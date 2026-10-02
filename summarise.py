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

Removed paragraphs that verify.py identifies as merge artifacts are skipped by
default: their text survives inside a consolidated paragraph, so summarising
them as removals would repeat the diff's own mistake in more confident prose.

Responses are cached on disk keyed by model, prompt version and change text,
so re-running during development costs nothing for changes already seen.

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

# Bump whenever the prompt or schema changes, so cached answers from an older
# prompt are not silently reused.
PROMPT_VERSION = "v1"  # checker changes do not need a bump: checks re-run on cached answers

CACHE_DIR = Path("cache/llm")
RESULTS_DIR = Path("results")

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
        "evidence": {
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
        },
    },
    "required": ["summary", "materiality", "materiality_reason", "evidence"],
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
_EDGE_PUNCT = " .,;:!?'\"\u2026"


def check_evidence(change: dict, evidence: list[dict]) -> dict:
    """
    Decide, in code, whether each quote really appears where the model said.

    A quote attributed to the wrong filing counts as unsupported even if the
    words exist in the other one: for an added or removed paragraph that is
    exactly the confusion that would produce a wrong summary.
    """
    sources = {
        "old": normalise(change.get("old") or ""),
        "new": normalise(change.get("new") or ""),
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
    return {"status": status, "evidence": checked}


# --------------------------------------------------------------------------- #
# Model call, with cache and cost accounting
# --------------------------------------------------------------------------- #

def build_user_message(change: dict) -> str:
    kind = change["kind"]
    parts = [f"CHANGE TYPE: {kind}"]
    if change.get("old"):
        parts.append(f"OLD:\n{change['old']}")
    if change.get("new"):
        parts.append(f"NEW:\n{change['new']}")
    return "\n\n".join(parts)


def cache_key(model: str, change: dict) -> str:
    payload = json.dumps(
        [PROMPT_VERSION, model, change["kind"], change.get("old"), change.get("new")],
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def call_model(client, model: str, change: dict) -> dict:
    """One structured-output request. Returns parsed JSON plus token usage."""
    response = client.messages.create(
        model=model,
        max_tokens=800,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_message(change)}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
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
        "check": check_evidence(change, parsed.get("evidence", [])),
        "input_tokens": raw["input_tokens"],
        "output_tokens": raw["output_tokens"],
        "cached": cached,
    }


# --------------------------------------------------------------------------- #
# Selecting changes
# --------------------------------------------------------------------------- #

def collect_changes(old_text: str, new_text: str, include_merges: bool = False):
    """
    Turn the diff into a flat list of changes to summarise.

    Merge artifacts are excluded unless asked for. See module docstring.
    """
    from verify import verify

    result, findings = verify(old_text, new_text)
    merge_artifacts = {
        f["removed"] for f in findings if f["verdict"] == "LIKELY MERGE ARTIFACT"
    }

    changes, skipped = [], []
    for p in result["added"]:
        changes.append({"kind": "added", "old": None, "new": p})
    for p in result["removed"]:
        if p in merge_artifacts and not include_merges:
            skipped.append(p)
            continue
        changes.append({"kind": "removed", "old": p, "new": None})
    for m in result["modified"]:
        changes.append({"kind": "modified", "old": m["old"], "new": m["new"],
                        "similarity": m["similarity"]})
    return changes, skipped


# --------------------------------------------------------------------------- #
# Digest
# --------------------------------------------------------------------------- #

ORDER = {"high": 0, "medium": 1, "low": 2}
BADGE = {"VERIFIED": "verified", "PARTIAL": "PARTLY VERIFIED", "UNSUPPORTED": "UNVERIFIED"}


def cost_usd(model: str, tokens_in: int, tokens_out: int) -> float | None:
    if model not in PRICES:
        return None
    p_in, p_out = PRICES[model]
    return tokens_in / 1e6 * p_in + tokens_out / 1e6 * p_out


def write_digest(ticker: str, item: str, model: str, rows: list[dict],
                 skipped: list[str]) -> Path:
    rows = sorted(rows, key=lambda r: (ORDER.get(r["materiality"], 3), r["kind"]))
    status_counts = {s: sum(r["check"]["status"] == s for r in rows) for s in BADGE}
    tokens_in = sum(r["input_tokens"] for r in rows)
    tokens_out = sum(r["output_tokens"] for r in rows)
    cost = cost_usd(model, tokens_in, tokens_out)
    fresh = [r for r in rows if not r["cached"]]
    fresh_cost = cost_usd(model, sum(r["input_tokens"] for r in fresh),
                          sum(r["output_tokens"] for r in fresh))

    lines = [
        f"# {ticker} Item {item}: what changed",
        "",
        f"Model `{model}`, prompt {PROMPT_VERSION}. {len(rows)} changes summarised.",
        "",
        "| check | count |", "|---|---|",
        *[f"| {BADGE[s]} | {n} |" for s, n in status_counts.items()],
        "",
        f"Tokens: {tokens_in:,} in / {tokens_out:,} out."
        + (f" Full-run cost ${cost:.4f}; this run ${fresh_cost:.4f} "
           f"({len(rows) - len(fresh)} from cache)." if cost is not None else ""),
        "",
    ]
    if skipped:
        lines += [
            f"{len(skipped)} removed paragraph(s) skipped as likely merge artifacts "
            "(their text survives in a consolidated paragraph; see verify.py).",
            "",
        ]

    for level in ("high", "medium", "low"):
        group = [r for r in rows if r["materiality"] == level]
        if not group:
            continue
        lines += [f"## {level.capitalize()} materiality ({len(group)})", ""]
        for r in group:
            status = r["check"]["status"]
            flag = "" if status == "VERIFIED" else f" **[{BADGE[status]}]**"
            lines.append(f"- **{r['kind'].upper()}**{flag} {r['summary']}")
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
        print(f"  {i:>3}/{len(changes)} {row['kind']:<8} {row['materiality']:<6} "
              f"{row['check']['status']:<11}{' (cached)' if row['cached'] else ''}")

    path = write_digest(args.ticker, args.item, args.model, rows, skipped)
    print(f"\nDigest written to {path}")


if __name__ == "__main__":
    main()
