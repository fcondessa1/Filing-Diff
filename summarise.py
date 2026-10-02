"""
Summarise each disclosure change with an LLM, and check every claim against
the filing text before trusting it.

Pipeline:

    diff2 -> one change at a time -> Claude -> {summary, materiality, evidence}
          -> every evidence quote checked verbatim against the source text
          -> digest of verified summaries, with failures flagged rather than hidden

The verification step is the point of this module. A summary is only as good
as its grounding, and a model asked to explain a legal paragraph will
sometimes paraphrase inside quotation marks or attribute wording to the wrong
filing. So the model must quote the exact words that support its summary, and
the code -- not the model -- decides whether those words exist:

    VERIFIED     every quote appears verbatim in the filing it was attributed to
    PARTIAL      some quotes found, some not
    UNSUPPORTED  no quote found, or no quotes given

Removals are judged, not trusted (prompt v2 for removed paragraphs).
The first full run (v1) showed that quote checking is not enough. The diff
pairs paragraphs one to one, so text a company merged, split or condensed
shows up as REMOVED. The model was shown only the old paragraph, had no way to
see where it went, and wrote fluent, fully verified summaries of removals that
had not happened -- four of the twelve high-materiality items, each contradicted
elsewhere in the same digest. Citation checks catch invented quotes, not wrong
conclusions.

So each removed paragraph is now sent with the two paragraphs in the new
filing that contain most of its content (by containment, from verify.py), and
the model must decide whether the risk was really removed, moved or reworded,
or partially removed. A "still disclosed" verdict must quote the new filing,
and that quote is checked like any other, so the model cannot claim the text
survived without showing where.

Removed paragraphs that verify.py identifies as merge artifacts are still
skipped by default: they survive almost word for word and do not need a model.

Responses are cached on disk keyed by model, prompt version and change text,
so re-running during development costs nothing for changes already seen.
Prompt versions are per change type, so revising the removal prompt does not
invalidate cached answers for added and modified paragraphs.

If a hand-verification file exists (results/aapl_fy2025_verification.txt by
default), the digest also scores the model's removal verdicts against it.

Setup:
    pip install -r requirements.txt
    export ANTHROPIC_API_KEY="sk-ant-..."     # never commit this

Usage:
    python summarise.py AAPL 1A --limit 5     # cheap first run
    python summarise.py AAPL 1A               # everything
    python summarise.py AAPL 1A --model claude-sonnet-5-5
"""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_MODEL = os.environ.get("FILING_DIFF_MODEL", "claude-haiku-4-5-20251001")

# USD per million tokens (input, output). From the Claude models overview page;
# update when prices change -- the cost line in the digest depends on it.
PRICES = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}

# Bump the version for a change type whenever its prompt or schema changes, so
# cached answers from an older prompt are not silently reused. Changes to the
# checker do not need a bump: checks re-run on cached answers.
PROMPT_VERSIONS = {"added": "v1", "modified": "v1", "removed": "v2"}

# How many surviving paragraphs to show the model for each removal. Two, so
# content split across two new paragraphs can still be recognised.
N_CANDIDATES = 2

CACHE_DIR = Path("cache/llm")
RESULTS_DIR = Path("results")
DEFAULT_LABELS = Path("results/aapl_fy2025_verification.txt")

EVIDENCE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "source": {"type": "string", "enum": ["old", "new"]},
            "quote": {"type": "string"},
        },
        "required": ["source", "quote"],
        "additionalProperties": False,
    },
}

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "One sentence: what the company changed in this disclosure.",
        },
        "materiality": {
            "type": "string",
            "enum": ["high", "medium", "low"],
        },
        "materiality_reason": {
            "type": "string",
            "description": "One sentence: why an investor would or would not care.",
        },
        "evidence": EVIDENCE_SCHEMA,
    },
    "required": ["summary", "materiality", "materiality_reason", "evidence"],
    "additionalProperties": False,
}

VERDICTS = ("removed", "moved_or_reworded", "partially_removed")

# Evidence first: the model locates the text before it commits to a verdict.
REMOVED_SCHEMA = {
    "type": "object",
    "properties": {
        "evidence": EVIDENCE_SCHEMA,
        "verdict": {"type": "string", "enum": list(VERDICTS)},
        "summary": {
            "type": "string",
            "description": "One sentence: what happened to this disclosure.",
        },
        "materiality": {
            "type": "string",
            "enum": ["high", "medium", "low"],
        },
        "materiality_reason": {
            "type": "string",
            "description": "One sentence: why an investor would or would not care about what was lost.",
        },
    },
    "required": ["evidence", "verdict", "summary", "materiality", "materiality_reason"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You analyse changes to the Risk Factors section of SEC 10-K filings for an individual investor.

You will be given one change between last year's filing (OLD) and this year's (NEW): a paragraph that was added, removed, or modified.

Rules:
- Describe only what changed. Do not summarise the parts that stayed the same.
- For a modified paragraph, name the specific words or ideas that were added, removed or softened.
- Do not speculate about why the company made the change unless the text itself says so.
- Materiality: "high" if it names a new risk, drops an existing risk, or materially changes its scope; "medium" if it changes emphasis or detail in a way an attentive investor would notice; "low" for wording, ordering or boilerplate.
- Evidence: give 1 to 3 quotes copied EXACTLY, character for character, from the text, each 5 to 30 words. Mark each quote "old" or "new" according to which text it was copied from. Never paraphrase inside a quote. Never quote text that is not shown to you.
- For an added paragraph, quotes can only come from NEW. For a removed paragraph, only from OLD."""

REMOVED_PROMPT = """You analyse changes to the Risk Factors section of SEC 10-K filings for an individual investor.

You will be given a paragraph from last year's filing (OLD) that an automated diff could not match to any paragraph in this year's filing, together with the paragraphs from this year's filing that share the most content with it (CANDIDATES).

The diff matches paragraphs one to one, so it reports text as removed when the company merged it into a longer paragraph, split it across paragraphs, or condensed it. Do not assume the diff is right. Decide whether the risk described in OLD is still disclosed in the CANDIDATES.

verdict:
- "removed": the risk in OLD is not disclosed in any candidate.
- "moved_or_reworded": the substance of OLD is still disclosed in a candidate, even if shortened, merged with other content, or reworded.
- "partially_removed": part of OLD survives in a candidate, but a specific risk, consequence or detail from OLD is no longer there.

Rules:
- Judge substance, not wording. A sentence that was condensed or merged into a longer paragraph still counts as disclosed.
- Shared boilerplate such as "could materially adversely affect the Company's business, results of operations and financial condition" does not count as the risk surviving.
- The candidates are only the closest matches that were found. If neither discloses the risk, the verdict is "removed".
- summary: one sentence on what happened to the disclosure. For "partially_removed", name exactly what was dropped. For "moved_or_reworded", say where it went.
- materiality: rate what was actually lost. Use "low" for "moved_or_reworded" unless the rewording materially changed the risk.
- Evidence: 1 to 3 quotes copied EXACTLY, character for character, each 5 to 30 words. Use source "old" for quotes from OLD and "new" for quotes from a CANDIDATE. Never paraphrase inside a quote.
- For "moved_or_reworded" or "partially_removed", at least one quote must come from a CANDIDATE, showing where the risk survives."""


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #

_QUOTE_CHARS = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", " ": " ", "®": "",
})


def normalise(text: str) -> str:
    """
    Make verbatim comparison robust to typography, not to wording.

    Filings use curly quotes and non-breaking spaces; models usually emit
    straight quotes. Treating those as different would flag faithful quotes
    as fabricated. Case and words are left alone deliberately.
    """
    return re.sub(r"\s+", " ", text.translate(_QUOTE_CHARS)).strip()


# Punctuation a model adds or drops at the edge of a quote. Found on the first
# live run: Claude quoted "...products, services and operations." where the
# filing continues "...operations, and may lead to...". The words were exact;
# only the closing full stop differed, and the strict check flagged a faithful
# quote as fabricated. Stripping boundary punctuation cannot change wording.
_EDGE_PUNCT = " .,;:!?'\"…"


def new_side_text(change: dict) -> str:
    """
    The text a "new" quote must come from.

    For a removal there is no matched new paragraph, so "new" means the
    candidate paragraphs the model was shown.
    """
    if change.get("new"):
        return change["new"]
    return "\n\n".join(c["text"] for c in change.get("candidates") or [])


def check_evidence(change: dict, evidence: list[dict], verdict: str | None = None) -> dict:
    """
    Decide, in code, whether each quote really appears where the model said.

    A quote attributed to the wrong filing counts as unsupported even if the
    words exist in the other one: for an added or removed paragraph that is
    exactly the confusion that would produce a wrong summary.

    For a removal judged "moved_or_reworded" or "partially_removed", the claim
    that the risk survives is only supported if at least one quote from the
    new filing was found. Otherwise the verdict is flagged.
    """
    sources = {
        "old": normalise(change.get("old") or ""),
        "new": normalise(new_side_text(change)),
    }
    checked = []
    for item in evidence:
        quote = normalise(item.get("quote", "")).strip(_EDGE_PUNCT)
        src = item.get("source")
        found = bool(quote) and src in sources and quote in sources[src]
        elsewhere = (not found and bool(quote)
                     and any(quote in text for text in sources.values()))
        checked.append({**item, "found": found, "wrong_source": elsewhere})

    n_found = sum(c["found"] for c in checked)
    if not checked or n_found == 0:
        status = "UNSUPPORTED"
    elif n_found == len(checked):
        status = "VERIFIED"
    else:
        status = "PARTIAL"

    if verdict is None:
        verdict_supported = None
    elif verdict == "removed":
        verdict_supported = True
    else:
        verdict_supported = any(c["found"] and c["source"] == "new" for c in checked)

    return {"status": status, "evidence": checked, "verdict_supported": verdict_supported}


# --------------------------------------------------------------------------- #
# Model call, with cache and cost accounting
# --------------------------------------------------------------------------- #

def build_user_message(change: dict) -> str:
    kind = change["kind"]
    if kind == "removed" and change.get("candidates") is not None:
        parts = ["CHANGE TYPE: removed (according to the diff)", f"OLD:\n{change['old']}"]
        for i, c in enumerate(change["candidates"], 1):
            parts.append(f"CANDIDATE {i} (from this year's filing):\n{c['text']}")
        if not change["candidates"]:
            parts.append("CANDIDATES: none found")
        return "\n\n".join(parts)

    parts = [f"CHANGE TYPE: {kind}"]
    if change.get("old"):
        parts.append(f"OLD:\n{change['old']}")
    if change.get("new"):
        parts.append(f"NEW:\n{change['new']}")
    return "\n\n".join(parts)


def cache_key(model: str, change: dict) -> str:
    """
    Added and modified changes use exactly the v1 key, so the cached answers
    from the first full run are reused. Removals include the candidates,
    because the answer depends on them.
    """
    kind = change["kind"]
    fields = [PROMPT_VERSIONS[kind], model, kind, change.get("old"), change.get("new")]
    if kind == "removed":
        fields.append([c["text"] for c in change.get("candidates") or []])
    payload = json.dumps(fields, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def call_model(client, model: str, change: dict) -> dict:
    """One structured-output request. Returns parsed JSON plus token usage."""
    judged_removal = change["kind"] == "removed" and change.get("candidates") is not None
    response = client.messages.create(
        model=model,
        max_tokens=800,
        system=REMOVED_PROMPT if judged_removal else SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_message(change)}],
        output_config={"format": {"type": "json_schema",
                                  "schema": REMOVED_SCHEMA if judged_removal else SCHEMA}},
    )
    text = next(b.text for b in response.content if b.type == "text")
    return {
        "parsed": json.loads(text),
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }


def summarise_change(client, model: str, change: dict, use_cache: bool = True) -> dict:
    key = cache_key(model, change)
    path = CACHE_DIR / f"{key}.json"

    if use_cache and path.exists():
        raw = json.loads(path.read_text())
        cached = True
    else:
        raw = call_model(client, model, change)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=1))
        cached = False

    parsed = raw["parsed"]
    return {
        **change,
        **parsed,
        "check": check_evidence(change, parsed.get("evidence", []), parsed.get("verdict")),
        "input_tokens": raw["input_tokens"],
        "output_tokens": raw["output_tokens"],
        "cached": cached,
    }


# --------------------------------------------------------------------------- #
# Selecting changes
# --------------------------------------------------------------------------- #

def find_candidates(removed: str, new_paras: list[str], idf: dict,
                    n: int = N_CANDIDATES) -> list[dict]:
    """The n new paragraphs holding the most of the removed paragraph's content."""
    from verify import containment

    scored = sorted(((containment(removed, p, idf), p) for p in new_paras),
                    key=lambda x: -x[0])
    return [{"text": p, "containment": round(s, 3)} for s, p in scored[:n] if s > 0]


def collect_changes(old_text: str, new_text: str, include_merges: bool = False):
    """
    Turn the diff into a flat list of changes to summarise.

    Merge artifacts are excluded unless asked for. Every other removal carries
    its candidate surviving paragraphs, for the model to judge.
    """
    from diff2 import split_paragraphs
    from idf import build_idf
    from verify import verify

    result, findings = verify(old_text, new_text)
    merge_artifacts = {
        f["removed"] for f in findings if f["verdict"] == "LIKELY MERGE ARTIFACT"
    }
    new_paras = split_paragraphs(new_text)
    idf = build_idf(split_paragraphs(old_text) + new_paras)

    changes, skipped = [], []
    for p in result["added"]:
        changes.append({"kind": "added", "old": None, "new": p})
    for p in result["removed"]:
        if p in merge_artifacts and not include_merges:
            skipped.append(p)
            continue
        changes.append({"kind": "removed", "old": p, "new": None,
                        "candidates": find_candidates(p, new_paras, idf)})
    for m in result["modified"]:
        changes.append({"kind": "modified", "old": m["old"], "new": m["new"],
                        "similarity": m["similarity"]})
    return changes, skipped


# --------------------------------------------------------------------------- #
# Scoring removal verdicts against hand verification
# --------------------------------------------------------------------------- #

def removal_key(text: str) -> str:
    return normalise(text)[:100]


def hand_label(raw: str) -> str | None:
    """
    Map a free-text verdict from verify.py's review file to a model verdict.
    PARTIAL is checked first: "REWORDED PARTIAL" means something was dropped.
    """
    v = raw.upper()
    if "PARTIAL" in v:
        return "partially_removed"
    if "REAL" in v:
        return "removed"
    if any(w in v for w in ("MERGED", "REWORDED", "SCATTERED", "SPLIT", "MOVED")):
        return "moved_or_reworded"
    return None


def load_hand_labels(path: Path) -> dict[str, str]:
    """
    Parse the verdicts written into verify.py's output by hand.

    Each entry is a "REMOVED (n chars):" block followed, a few lines later, by
    "your verdict: ...". Entries left blank or unrecognised are skipped.
    """
    if not path or not Path(path).exists():
        return {}
    text = Path(path).read_text()
    labels = {}
    for block in re.split(r"\n--- \d+\.", text)[1:]:
        m_text = re.search(r"REMOVED \(\d+ chars\):\n(.*?)\n\n", block, re.S)
        m_verdict = re.search(r"your verdict:\s*(.+)", block)
        if not (m_text and m_verdict):
            continue
        label = hand_label(m_verdict.group(1))
        if label:
            labels[removal_key(m_text.group(1))] = label
    return labels


def score_removals(rows: list[dict], labels: dict[str, str]) -> dict | None:
    """
    Compare the model's removal verdicts with hand verification.

    The baseline is the diff on its own, which calls every one of them removed.
    """
    pairs = []
    for r in rows:
        if r["kind"] != "removed" or not r.get("verdict"):
            continue
        hand = labels.get(removal_key(r["old"]))
        if hand:
            pairs.append((r, hand))
    if not pairs:
        return None
    return {
        "pairs": pairs,
        "model_agree": sum(r["verdict"] == hand for r, hand in pairs),
        "diff_agree": sum(hand == "removed" for _, hand in pairs),
        "n": len(pairs),
    }


# --------------------------------------------------------------------------- #
# Digest
# --------------------------------------------------------------------------- #

ORDER = {"high": 0, "medium": 1, "low": 2}
BADGE = {"VERIFIED": "verified", "PARTIAL": "PARTLY VERIFIED", "UNSUPPORTED": "UNVERIFIED"}
VERDICT_LABEL = {
    "removed": "REMOVED",
    "moved_or_reworded": "NOT REMOVED (moved or reworded)",
    "partially_removed": "PARTLY REMOVED",
}


def cost_usd(model: str, tokens_in: int, tokens_out: int) -> float | None:
    if model not in PRICES:
        return None
    p_in, p_out = PRICES[model]
    return tokens_in / 1e6 * p_in + tokens_out / 1e6 * p_out


def row_label(r: dict) -> str:
    if r["kind"] == "removed" and r.get("verdict"):
        return VERDICT_LABEL[r["verdict"]]
    return r["kind"].upper()


def write_digest(ticker: str, item: str, model: str, rows: list[dict],
                 skipped: list[str], labels: dict[str, str] | None = None) -> Path:
    rows = sorted(rows, key=lambda r: (ORDER.get(r["materiality"], 3), r["kind"]))
    status_counts = {s: sum(r["check"]["status"] == s for r in rows) for s in BADGE}
    tokens_in = sum(r["input_tokens"] for r in rows)
    tokens_out = sum(r["output_tokens"] for r in rows)
    cost = cost_usd(model, tokens_in, tokens_out)
    fresh = [r for r in rows if not r["cached"]]
    fresh_cost = cost_usd(model, sum(r["input_tokens"] for r in fresh),
                          sum(r["output_tokens"] for r in fresh))
    versions = ", ".join(f"{k} {v}" for k, v in PROMPT_VERSIONS.items())

    lines = [
        f"# {ticker} Item {item}: what changed",
        "",
        f"Model `{model}`, prompts: {versions}. {len(rows)} changes summarised.",
        "",
        "| check | count |", "|---|---|",
        *[f"| {BADGE[s]} | {n} |" for s, n in status_counts.items()],
        "",
        f"Tokens: {tokens_in:,} in / {tokens_out:,} out."
        + (f" Full-run cost ${cost:.4f}; this run ${fresh_cost:.4f} "
           f"({len(rows) - len(fresh)} from cache)." if cost is not None else ""),
        "",
    ]

    judged = [r for r in rows if r["kind"] == "removed" and r.get("verdict")]
    if judged or skipped:
        n_flagged = len(judged) + len(skipped)
        counts = {v: sum(r["verdict"] == v for r in judged) for v in VERDICTS}
        lines += [
            f"**Removals.** The diff flagged {n_flagged} paragraphs as removed. "
            f"{len(skipped)} were skipped as merge artifacts (their text survives in a "
            f"consolidated paragraph; see verify.py). The model judged the other "
            f"{len(judged)} against the closest surviving text: "
            f"{counts['removed']} removed, {counts['moved_or_reworded']} moved or reworded, "
            f"{counts['partially_removed']} partly removed.",
            "",
        ]

    score = score_removals(rows, labels or {})
    if score:
        lines += [
            f"**Against hand verification**, the model's removal verdict matched "
            f"{score['model_agree']} of {score['n']}. Taking the diff's label at face "
            f"value would have matched {score['diff_agree']} of {score['n']}.",
            "",
            "| paragraph | hand | model | match |", "|---|---|---|---|",
        ]
        for r, hand in score["pairs"]:
            start = normalise(r["old"])[:60].replace("|", "/")
            mark = "✓" if r["verdict"] == hand else "✗"
            lines.append(f"| {start}… | {hand} | {r['verdict']} | {mark} |")
        lines.append("")

    for level in ("high", "medium", "low"):
        group = [r for r in rows if r["materiality"] == level]
        if not group:
            continue
        lines += [f"## {level.capitalize()} materiality ({len(group)})", ""]
        for r in group:
            status = r["check"]["status"]
            flags = "" if status == "VERIFIED" else f" **[{BADGE[status]}]**"
            if r["check"].get("verdict_supported") is False:
                flags += " **[VERDICT UNSUPPORTED: no quote from the new filing found]**"
            lines.append(f"- **{row_label(r)}**{flags} {r['summary']}")
            lines.append(f"  - *Why it matters:* {r['materiality_reason']}")
            for e in r["check"]["evidence"]:
                mark = "✓" if e["found"] else ("✗ wrong filing" if e["wrong_source"] else "✗ not found")
                lines.append(f"  - {mark} ({e['source']}) \"{e['quote']}\"")
            lines.append("")

    RESULTS_DIR.mkdir(exist_ok=True)
    stem = f"{ticker.lower()}_{item.lower()}_digest"
    md_path = RESULTS_DIR / f"{stem}.md"
    md_path.write_text("\n".join(lines))
    (RESULTS_DIR / f"{stem}.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1)
    )
    return md_path


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ticker", nargs="?", default="AAPL")
    ap.add_argument("item", nargs="?", default="1A")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--limit", type=int, default=None,
                    help="only summarise the first N changes (cheap test runs)")
    ap.add_argument("--include-merges", action="store_true",
                    help="also summarise removals that verify.py flags as merge artifacts")
    ap.add_argument("--labels", type=Path, default=DEFAULT_LABELS,
                    help="hand-verified verify.py output to score removal verdicts against")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY first (see the module docstring).")

    from anthropic import Anthropic
    from run_diff import load_pair

    old_text, new_text = load_pair(args.ticker, args.item)
    changes, skipped = collect_changes(old_text, new_text, args.include_merges)
    if args.limit:
        changes = changes[: args.limit]

    print(f"\nSummarising {len(changes)} changes with {args.model}"
          f"{f' ({len(skipped)} merge artifacts skipped)' if skipped else ''}...")

    client = Anthropic()
    rows = []
    for i, change in enumerate(changes, 1):
        row = summarise_change(client, args.model, change, use_cache=not args.no_cache)
        rows.append(row)
        label = row.get("verdict") or row["materiality"]
        print(f"  {i:>3}/{len(changes)} {row['kind']:<8} {label:<18} "
              f"{row['check']['status']:<11}{' (cached)' if row['cached'] else ''}")

    labels = load_hand_labels(args.labels)
    path = write_digest(args.ticker, args.item, args.model, rows, skipped, labels)
    print(f"\nDigest written to {path}")
    score = score_removals(rows, labels)
    if score:
        print(f"Removal verdicts vs hand verification: model {score['model_agree']}/{score['n']}, "
              f"diff label alone {score['diff_agree']}/{score['n']}")


if __name__ == "__main__":
    main()
