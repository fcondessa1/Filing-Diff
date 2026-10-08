"""
Answer questions across a company's filings, with every claim checked against
the passage it cites.

    question -> hybrid search (store.py) -> top passages, oldest first
             -> Claude: answer + claims, each citing passage ids and exact quotes
             -> code checks each quote exists in the passage it cites
             -> answer printed with ✓ / ✗ per citation, saved to results/qa/

Two lessons from summarise.py carry over. First, the model must quote, and
the code decides whether the quote exists, so an invented quote or a citation
to the wrong passage is caught. Second, a verified quote does not make a claim
true: the summariser produced fully verified summaries of removals that had
not happened. Here the main defence is the retrieval itself (you can read the
passages the answer rests on), plus an explicit "not in sources" option so the
model is not pushed into answering from passages that do not contain the
answer.

Passages are shown to the model oldest first, labelled with filing date and
form, because the useful questions are about change over time ("what has
Apple said about tariffs over the last two years?").

Usage:
    python ask.py AAPL "What has Apple said about tariffs?"
    python ask.py AAPL "How could the Google antitrust case affect revenue?" --k 15
"""

import argparse
import os
import re
import sys
from pathlib import Path

from summarise import _EDGE_PUNCT, cost_usd, normalise, response_json

# Questions default to a larger model than the summariser. On the first
# cross-filing question ("what has Apple said about tariffs over the last two
# years?"), Haiku and Sonnet were given the same 12 passages. All runs verified
# every claim. Haiku left out the new Section 122 and Section 301 tariffs and
# ended on the Supreme Court refunds, implying tariffs were being wound down.
# Sonnet ended on the latest position in both of two runs and named Section
# 301 in both, but Section 122 in only one: the same model, prompt and
# passages give different answers from run to run, so one run per model is
# not a comparison. Citation checks cannot catch an omission, so model choice
# is a partial defence, not a fix. Sonnet costs about 2.4 cents per question
# against 0.9; the summariser's 63 calls per filing stay on Haiku.
ASK_MODEL = os.environ.get("FILING_DIFF_ASK_MODEL", "claude-sonnet-5-5")

QA_DIR = Path("results/qa")
DEFAULT_K = 12

SCHEMA = {
    "type": "object",
    "properties": {
        "coverage": {
            "type": "string",
            "enum": ["answered", "partially_answered", "not_in_sources"],
        },
        "answer": {
            "type": "string",
            "description": "2 to 6 plain sentences answering the question from the passages.",
        },
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "citations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "passage_id": {"type": "integer"},
                                "quote": {"type": "string"},
                            },
                            "required": ["passage_id", "quote"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["statement", "citations"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["coverage", "answer", "claims"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You answer an individual investor's questions about a company using excerpts from its SEC filings (10-K annual reports and 10-Q quarterly reports).

The excerpts are numbered passages, listed oldest first, each labelled with its filing date, form and section. Use only these passages. Do not use outside knowledge about the company, even if you are confident it is true.

Rules:
- coverage: "answered" if the passages answer the question; "partially_answered" if they cover only part of it; "not_in_sources" if they do not answer it. If "not_in_sources", say so plainly in the answer and give no claims. Do not stretch loosely related passages into an answer.
- answer: 2 to 6 plain sentences. When the question is about change over time, say when things changed, using the filing dates. Some passages say that versions of the paragraph appear in several filings, with the first and last filing dates: use those dates for when a statement first appeared and how long it continued.
- claims: break the answer into its factual claims. Every claim needs at least one citation.
- citations: the passage_id and a quote copied EXACTLY, character for character, from that passage, 5 to 30 words. Never paraphrase inside a quote. Never cite a passage for words it does not contain.
- Filings describe risks as possibilities. Do not turn "could" or "may" into "will" or "has"."""


# --------------------------------------------------------------------------- #
# Prompt and verification
# --------------------------------------------------------------------------- #

def chronological(passages: list[dict]) -> list[dict]:
    return sorted(passages, key=lambda p: (p["filing_date"], p["id"]))


def format_passages(passages: list[dict]) -> str:
    section_name = {"risk_factors": "Risk Factors", "mdna": "MD&A"}
    blocks = []
    for p in chronological(passages):
        label = section_name.get(p["section"], p["section"])
        header = f"[{p['id']}] {p['form']} filed {p['filing_date']}, {label}"
        span = p.get("span")
        if span:
            header += (f" (a version of this paragraph appears in {span['versions']} filings, "
                       f"from the {span['first'][0]} filed {span['first'][1]} "
                       f"to the {span['last'][0]} filed {span['last'][1]})")
        blocks.append(f"{header}\n{p['text']}")
    return "\n\n".join(blocks)


def check_answer(parsed: dict, passages: list[dict]) -> dict:
    """
    Check each citation in code: the passage must be one the model was shown,
    and the quote must appear in that passage.
    """
    texts = {p["id"]: normalise(p["text"]) for p in passages}
    claims = []
    for claim in parsed.get("claims", []):
        cites = []
        for c in claim.get("citations", []):
            quote = normalise(c.get("quote", "")).strip(_EDGE_PUNCT)
            pid = c.get("passage_id")
            if pid not in texts:
                problem = "cites a passage that was not provided"
            elif not quote or quote not in texts[pid]:
                elsewhere = [i for i, t in texts.items() if quote and quote in t]
                problem = (f"quote is in passage {elsewhere[0]}, not {pid}" if elsewhere
                           else "quote not found in passage")
            else:
                problem = None
            cites.append({**c, "found": problem is None, "problem": problem})
        n_ok = sum(c["found"] for c in cites)
        status = ("UNSUPPORTED" if not cites or n_ok == 0
                  else "VERIFIED" if n_ok == len(cites) else "PARTIAL")
        claims.append({**claim, "citations": cites, "status": status})

    counts = {s: sum(c["status"] == s for c in claims)
              for s in ("VERIFIED", "PARTIAL", "UNSUPPORTED")}
    return {"claims": claims, "counts": counts}


# --------------------------------------------------------------------------- #
# Ask
# --------------------------------------------------------------------------- #

def ask(client, conn, embedder, ticker: str, question: str,
        k: int = DEFAULT_K, model: str = ASK_MODEL) -> dict:
    from store import CANDIDATES, collapse_versions, fts_query, keyword_ranking, search

    # Retrieve deeper than needed, then collapse repeated versions of the same
    # paragraph so the k slots go to distinct passages (see store.py). Slots
    # freed that way go only to passages containing a topic word from the
    # question; if the question has none (all filler or time words), there is
    # nothing to check against and freed slots are filled as ranked.
    candidates = search(conn, embedder, ticker, question, k=max(k, CANDIDATES))
    on_topic = (set(keyword_ranking(conn, ticker, question, limit=100_000))
                if fts_query(question) else None)
    passages = collapse_versions(candidates, k, eligible_extra=on_topic)
    if not passages:
        return {"question": question, "passages": [], "error": "no passages found"}

    response = client.messages.create(
        model=model,
        # Was 1,500: a run used 1,465, the next needed more and was cut off
        # mid-JSON. Output is billed by tokens used, not by this cap.
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content":
                   f"PASSAGES:\n\n{format_passages(passages)}\n\nQUESTION: {question}"}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    parsed = response_json(response)
    return {
        "question": question,
        "ticker": ticker.upper(),
        "model": model,
        "passages": chronological(passages),
        **parsed,
        "check": check_answer(parsed, passages),
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }


def render(result: dict) -> str:
    if result.get("error"):
        return f"# {result['question']}\n\n{result['error']}\n"
    by_id = {p["id"]: p for p in result["passages"]}
    counts = result["check"]["counts"]
    cost = cost_usd(result["model"], result["input_tokens"], result["output_tokens"])
    lines = [
        f"# {result['question']}",
        "",
        f"{result['ticker']} · {len(result['passages'])} passages · model `{result['model']}` · "
        f"coverage: **{result['coverage']}**",
        "",
        result["answer"],
        "",
        f"## Claims ({counts['VERIFIED']} verified, {counts['PARTIAL']} partly verified, "
        f"{counts['UNSUPPORTED']} unverified)",
        "",
    ]
    for c in result["check"]["claims"]:
        flag = "" if c["status"] == "VERIFIED" else f" **[{c['status']}]**"
        lines.append(f"- {c['statement']}{flag}")
        for cite in c["citations"]:
            p = by_id.get(cite["passage_id"])
            where = f"{p['form']} {p['filing_date']}" if p else f"passage {cite['passage_id']}"
            mark = "✓" if cite["found"] else f"✗ {cite['problem']}"
            lines.append(f"  - {mark} [{cite['passage_id']}] {where}: \"{cite['quote']}\"")
    lines += ["", "## Passages retrieved", ""]
    for p in result["passages"]:
        span = p.get("span")
        seen = (f" *(versions in {span['versions']} filings, {span['first'][1]} → "
                f"{span['last'][1]})*" if span else "")
        lines.append(f"- [{p['id']}] {p['form']} {p['filing_date']} {p['section']}{seen}: "
                     f"{p['text'][:160]}…")
    if cost is not None:
        lines += ["", f"Tokens: {result['input_tokens']:,} in / {result['output_tokens']:,} out "
                  f"(${cost:.4f})."]
    return "\n".join(lines) + "\n"


def save(result: dict) -> Path:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", result["question"].lower()).strip("-")[:60]
    # The model is part of the name, so asking the same question with a
    # different model keeps both answers for comparison.
    model = re.sub(r"[^a-z0-9]+", "-", result.get("model", "model").lower())
    model = re.sub(r"^claude-|-\d{8}$", "", model)
    path = QA_DIR / f"{result.get('ticker', 'x').lower()}_{slug}_{model}.md"
    path.write_text(render(result))
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ticker")
    ap.add_argument("question")
    ap.add_argument("--k", type=int, default=DEFAULT_K, help="passages to retrieve")
    ap.add_argument("--model", default=ASK_MODEL)
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY first.")

    from anthropic import Anthropic
    from store import Embedder, connect

    result = ask(Anthropic(), connect(), Embedder(), args.ticker, args.question,
                 k=args.k, model=args.model)
    print(render(result))
    print(f"Saved to {save(result)}")


if __name__ == "__main__":
    main()
