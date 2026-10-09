"""
Weekly digest: what changed in the Risk Factors of the companies I watch.

For each ticker in watchlist.txt:

    EDGAR -> any 10-K or 10-Q filed since the last run?
          -> compare its Risk Factors (Item 1A) with the previous filing of
             the same form: 10-K against 10-K, 10-Q against 10-Q
          -> the existing pipeline: diff, merge detection, removals judged
             against surviving text, every quote checked (summarise.py)
          -> results/digests/<date>.md, and a GitHub issue if anything is new

Runs weekly on GitHub's servers (.github/workflows/weekly-digest.yml), so
nothing needs to be left running. Filings arrive about once a quarter per
company, so most weeks report nothing and make no API calls.

Why 10-Q is compared with 10-Q, not with the last 10-K. A 10-Q's Risk Factors
section lists only updates to the annual report's risk factors, not the full
set. Diffing it against a 10-K would report every risk factor the 10-Q does
not repeat as removed. Two 10-Qs list updates in the same way, so comparing
them shows what changed since last quarter. Some 10-Qs only say there were
no material changes, or list only the updates; process_filing handles both
(see its docstring) rather than reporting a removal of everything.

State. results/digests/state.json records which filings have been processed
per ticker. A ticker's first run records every filing currently listed as
the baseline and reports nothing, so adding a company does not trigger a
summary of its history. --force-latest processes the latest filing anyway (for testing). A
filing whose processing fails is not recorded, so it is retried next week.

Usage:
    python digest.py                   # what the weekly job runs
    python digest.py --force-latest    # summarise each ticker's latest filing now
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

WATCHLIST = Path("watchlist.txt")
DIGEST_DIR = Path("results/digests")
STATE_PATH = DIGEST_DIR / "state.json"
LOOKBACK = 12          # filings fetched per ticker to find new ones and their predecessors
ITEM = "1A"


# --------------------------------------------------------------------------- #
# Watchlist and state
# --------------------------------------------------------------------------- #

def load_watchlist(path: Path = WATCHLIST) -> list[str]:
    """One ticker per line; blank lines and # comments ignored."""
    if not path.exists():
        sys.exit(f"{path} not found. Create it with one ticker per line, e.g. AAPL.")
    tickers = []
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip().upper()
        if line and line not in tickers:
            tickers.append(line)
    return tickers


def load_state(path: Path | None = None) -> dict:
    path = path or STATE_PATH      # looked up at call time, not definition time
    return json.loads(path.read_text()) if path.exists() else {}


def save_state(state: dict, path: Path | None = None) -> None:
    path = path or STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1, sort_keys=True))


# --------------------------------------------------------------------------- #
# Finding new filings and what to compare them with
# --------------------------------------------------------------------------- #

def new_filings(filings: list[dict], seen: list[str] | None, force_latest: bool) -> list[dict]:
    """
    Filings to process, oldest first. filings is newest first, as EDGAR lists
    them. seen is None on a ticker's first run: nothing is processed then,
    unless force_latest, and the latest filing becomes the baseline.
    """
    if not filings:
        return []
    if seen is None:
        return [filings[0]] if force_latest else []
    fresh = [f for f in filings if f["accession"] not in set(seen)]
    if force_latest and not fresh:
        fresh = [filings[0]]
    return list(reversed(fresh))


def previous_of_same_form(filings: list[dict], filing: dict) -> dict | None:
    """The next older filing with the same form (10-K -> 10-K, 10-Q -> 10-Q)."""
    older = filings[filings.index(filing) + 1:]
    return next((f for f in older if f["form"] == filing["form"]), None)


# --------------------------------------------------------------------------- #
# Processing one filing
# --------------------------------------------------------------------------- #

STATEMENT_MAX = 1000   # characters; "no changes" statements seen were 200 to 700


def risk_factors(url: str) -> str | None:
    """
    The Item 1A text, or None if no Item 1A heading was found at all.

    Short sections are returned too: a 10-Q's Item 1A is often a single
    sentence saying there were no material changes since the 10-K, and that
    has to be told apart from a heading the extractor could not find.
    """
    from edgar import fetch_document
    from sections import extract_sections

    return extract_sections(fetch_document(url), items=(ITEM,), min_chars=100).get(ITEM)


def is_statement(text: str) -> bool:
    """
    A short Item 1A that states there is nothing to report, rather than
    listing risks: "There have been no material changes to the risk factors
    disclosed in our Annual Report...". An updates section also says "no
    material changes", but "other than as set forth below", so a mention of
    what follows means there are risks to read.
    """
    return (len(text) < STATEMENT_MAX
            and re.search(r"no material change", text, re.IGNORECASE) is not None
            and re.search(r"\b(below|following)\b", text, re.IGNORECASE) is None)


def quote_statement(text: str) -> str:
    body = re.sub(r"^item\s*1a\W*(risk factors\W*)?", "", text.strip(), flags=re.IGNORECASE)
    body = re.sub(r"\s+", " ", body).strip()
    return f"> {body[:400]}{'…' if len(body) > 400 else ''}"


# --------------------------------------------------------------------------- #
# Joining headlines and page-break fragments before the diff
# --------------------------------------------------------------------------- #

HEADLINE_MAX = 400     # characters; risk factor headlines seen were 170 to 350
_PAGE_FURNITURE = re.compile(r"^(\d{1,3}|table\s+of\s+contents|page \d+)$", re.IGNORECASE)
# "Table of Contents" page links glued to the text around them (Amazon).
_TOC_LINK = re.compile(r"^table\s+of\s+contents\s+|\s+table\s+of\s+contents$", re.IGNORECASE)
_ENDS_SENTENCE = re.compile(r"[.!?:;][\"”’)]*$")
_INNER_SENTENCE_BREAK = re.compile(r"[.!?][\"”’)]*\s+[A-Z]")


def is_headline(paragraph: str) -> bool:
    """
    One short sentence starting with a capital: how filers write each risk
    factor's bold title. Not a bullet point (Amazon's lists end in a full
    stop), not an Item heading, and not the section's opening statement
    ("Other than the risk factors listed below, there have been no material
    changes..."), which introduces the whole section, not the next paragraph.
    """
    p = paragraph.strip()
    return (len(p) <= HEADLINE_MAX and p[:1].isupper() and p.endswith((".", "?", "!"))
            and _INNER_SENTENCE_BREAK.search(p) is None
            and not re.match(r"item\s*\d", p, re.IGNORECASE)
            and "no material change" not in p.lower())


def is_body(paragraph: str) -> bool:
    """
    Text a headline can be joined to: ends a sentence and is not itself a
    headline. Rules out subheadings such as Microsoft's "Competition in the
    technology sector" or Alphabet's "Risks Specific to our Company", which
    sit between a headline and its body or between groups of risks.
    """
    return _ENDS_SENTENCE.search(paragraph.strip()) is not None and not is_headline(paragraph)


def join_fragments(text: str) -> str:
    """
    Rejoin text that the HTML split into separate paragraphs, so the diff
    compares one unit per risk factor.

    Two cases, both seen on the first eight-company digest:

    1. Headline and body. Each risk factor is a one-sentence bold title
       followed by its explanation. Diffed separately, a new risk produced
       two near-identical summaries (IonQ: "cyclical", "sales cycles",
       "cancellable purchase orders" each twice; Alphabet's $40 billion
       share sale three times). A headline is joined to the paragraph after
       it when that is body text (see is_headline and is_body for what the
       first check on real filings showed these need to exclude).
    2. Page breaks. A sentence running across a page break became two
       paragraphs, and the second half was summarised as a change ("ending
       mid-sentence at 'penalties available'"). A paragraph that does not end
       a sentence is joined to the next one when that starts in lower case.
       Page numbers and "Table of Contents" links between them are dropped,
       including links glued to the text (Amazon: "Table of Contents
       ultimately take a view contrary to ours.").

    Used by the digest only; the Apple results in the README were produced
    without it.
    """
    paras = [_TOC_LINK.sub("", p.strip()).strip() for p in re.split(r"\n\s*\n", text)]
    paras = [p for p in paras if p and not _PAGE_FURNITURE.match(p)]

    # Page-break continuations first, so a headline split across pages is whole.
    joined: list[str] = []
    for p in paras:
        if joined and not _ENDS_SENTENCE.search(joined[-1]) and p[:1].islower():
            joined[-1] = f"{joined[-1]} {p}"
        else:
            joined.append(p)

    out: list[str] = []
    i = 0
    while i < len(joined):
        p = joined[i]
        nxt = joined[i + 1] if i + 1 < len(joined) else None
        if nxt and is_headline(p) and is_body(nxt):
            out.append(f"{p} {nxt}")
            i += 2
        else:
            out.append(p)
            i += 1
    return "\n\n".join(out)


def process_filing(client, model: str, filing: dict, previous: dict | None,
                   company: str | None = None) -> dict:
    """
    Compare one new filing with its predecessor and summarise the changes.

    10-Q Item 1A sections come in three shapes, seen on the first live run:
      - full risk factors every quarter (NVDA, GOOGL, LEU, AMZN)
      - one sentence: no material changes since the 10-K (IONQ and QBTS in Q1)
      - only the updates: "Other than as set forth below, there have been no
        material changes" followed by the new risks (IONQ and QBTS in Q2)
    A statement is reported as such, not diffed. When the previous 10-Q was a
    statement, everything in an updates section is new since last quarter, so
    it is compared against nothing and every paragraph is reported as added.
    """
    from summarise import collect_changes, summarise_change

    base = {"filing": filing, "previous": previous, "rows": [], "skipped": [], "note": None}
    if previous is None:
        return {**base, "note": f"No earlier {filing['form']} in the last {LOOKBACK} filings "
                                f"to compare with."}

    new_text, old_text = risk_factors(filing["url"]), risk_factors(previous["url"])
    if not new_text or not old_text:
        # Every 10-K and 10-Q has an Item 1A heading, even if all it says is
        # "no material changes", so no heading at all is an extraction
        # failure, not news about the company.
        which = ("this filing" if not new_text
                 else f"the {previous['form']} filed {previous['filing_date']}")
        return {**base, "extraction_failed": True,
                "note": (f"**Could not find the Risk Factors heading (Item 1A) in {which}.** "
                         f"Every 10-K and 10-Q has one, so this is a parsing failure, not a "
                         f"change. Check the filing by hand.")}

    if is_statement(new_text):
        return {**base, "note": "No changes reported. This filing's Risk Factors section "
                                "says:\n\n" + quote_statement(new_text)}

    note = None
    if is_statement(old_text):
        old_text = ""
        note = (f"The {previous['form']} filed {previous['filing_date']} reported no changes to "
                f"its risk factors, so every risk factor in this filing's section is new since "
                f"then and is listed as added.")

    changes, skipped = collect_changes(join_fragments(old_text), join_fragments(new_text))
    if company:
        changes = [{**c, "company": company} for c in changes]
    rows = [summarise_change(client, model, c) for c in changes]
    return {**base, "rows": rows, "skipped": skipped,
            "note": note if rows else "No changes to Risk Factors."}


# --------------------------------------------------------------------------- #
# Writing the digest
# --------------------------------------------------------------------------- #

def filing_section(ticker: str, result: dict, model: str) -> list[str]:
    from summarise import BADGE, ORDER, cost_usd, row_label

    f, prev = result["filing"], result["previous"]
    against = f" vs {prev['form']} filed {prev['filing_date']}" if prev else ""
    lines = [f"### {ticker} {f['form']} filed {f['filing_date']}{against}",
             "", f"[Filing on EDGAR]({f['url']})", ""]
    if result["note"]:
        lines += [result["note"], ""]
    if not result["rows"]:
        return lines

    rows = sorted(result["rows"], key=lambda r: ORDER.get(r["materiality"], 3))
    by_level = {lvl: [r for r in rows if r["materiality"] == lvl] for lvl in ("high", "medium", "low")}
    verified = sum(r["check"]["status"] == "VERIFIED" for r in rows)
    cost = cost_usd(model, sum(r["input_tokens"] for r in rows), sum(r["output_tokens"] for r in rows))
    lines += [
        f"{len(rows)} changes: {len(by_level['high'])} high, {len(by_level['medium'])} medium, "
        f"{len(by_level['low'])} low materiality. Quotes verified for {verified} of {len(rows)}."
        + (f" {len(result['skipped'])} merge artifacts skipped." if result["skipped"] else "")
        + (f" Cost ${cost:.3f}." if cost is not None else ""),
        "",
    ]
    for level in ("high", "medium"):
        for r in by_level[level]:
            status = r["check"]["status"]
            flags = "" if status == "VERIFIED" else f" **[{BADGE[status]}]**"
            if r["check"].get("verdict_supported") is False:
                flags += " **[VERDICT UNSUPPORTED]**"
            lines.append(f"- **{level.upper()} · {row_label(r)}**{flags} {r['summary']}")
            lines.append(f"  - {r['materiality_reason']}")
    if by_level["low"]:
        lines.append(f"- {len(by_level['low'])} low-materiality wording changes "
                     f"(listed in the JSON alongside this digest).")
    return lines + [""]


def write_digest(date: str, results: dict[str, list[dict]], errors: dict[str, str],
                 baselines: list[str], model: str) -> tuple[Path, bool, str]:
    """Returns the digest path, whether there is news, and an issue title."""
    processed = [(t, r) for t, rs in results.items() for r in rs]
    news = bool(processed or errors)
    lines = [f"# Filing digest, {date}", ""]

    if not news:
        lines.append("No new 10-K or 10-Q filings this week.")
    for ticker, result in processed:
        lines += filing_section(ticker, result, model)
    if errors:
        lines += ["## Errors", "", "These filings were not recorded as processed and will be "
                  "retried next week.", ""]
        lines += [f"- **{t}**: {msg}" for t, msg in errors.items()] + [""]
    if baselines:
        lines += [f"First run for {', '.join(baselines)}: latest filing recorded as the "
                  f"starting point. Changes are reported from the next filing on.", ""]

    DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    # A second run on the same day (a manual re-run) gets its own file
    # instead of replacing the first: 2026-10-08.md, then 2026-10-08-2.md.
    stem, n = date, 1
    while (DIGEST_DIR / f"{stem}.md").exists():
        n += 1
        stem = f"{date}-{n}"
    path = DIGEST_DIR / f"{stem}.md"
    path.write_text("\n".join(lines))
    (DIGEST_DIR / f"{stem}.json").write_text(json.dumps(
        {t: rs for t, rs in results.items()}, ensure_ascii=False, indent=1, default=str))

    parts = [f"{t} {r['filing']['form']}" + (" (extraction failed)" if r.get("extraction_failed") else "")
             for t, r in processed] + [f"{t} error" for t in errors]
    title = f"Filing digest {date}: " + (", ".join(parts) if parts else "nothing new")
    return path, news, title


# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #

def run(client, model: str, tickers: list[str], force_latest: bool = False,
        today: str | None = None) -> tuple[Path, bool, str]:
    from edgar import get_cik, list_filings

    date = today or dt.date.today().isoformat()
    state = load_state()
    results: dict[str, list[dict]] = {}
    errors: dict[str, str] = {}
    baselines: list[str] = []

    for ticker in tickers:
        try:
            filings = list_filings(get_cik(ticker), form_types=("10-K", "10-Q"), limit=LOOKBACK)
        except Exception as e:  # one bad ticker must not stop the digest
            errors[ticker] = f"could not list filings ({type(e).__name__}: {e})"
            continue

        seen = state.get(ticker)
        todo = new_filings(filings, seen, force_latest)
        if seen is None:
            # First run: everything currently listed is the starting point.
            # Recording only the latest would make the older ones look new
            # next week and summarise the whole lookback window.
            seen = [f["accession"] for f in filings]
            if not force_latest:
                state[ticker] = seen
                baselines.append(ticker)
                continue

        done = list(seen)
        for filing in todo:
            print(f"{ticker}: {filing['form']} filed {filing['filing_date']}")
            try:
                result = process_filing(client, model, filing, previous_of_same_form(filings, filing),
                                        company=ticker)
            except Exception as e:
                errors[ticker] = (f"{filing['form']} filed {filing['filing_date']}: "
                                  f"{type(e).__name__}: {e}")
                break  # keep later filings for next week, in order
            results.setdefault(ticker, []).append(result)
            if filing["accession"] not in done:
                done.append(filing["accession"])
        state[ticker] = done

    save_state(state)
    return write_digest(date, results, errors, baselines, model)


def main():
    ap = argparse.ArgumentParser(description="Weekly filing digest")
    ap.add_argument("--force-latest", action="store_true",
                    help="process each ticker's latest filing even if already seen (testing)")
    ap.add_argument("--model", default=None, help="defaults to the summariser's model")
    args = ap.parse_args()

    from summarise import DEFAULT_MODEL

    model = args.model or DEFAULT_MODEL
    tickers = load_watchlist()
    client = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        from anthropic import Anthropic
        client = Anthropic()

    class NoClient:  # fails only if a model call is actually needed
        class messages:
            @staticmethod
            def create(**_):
                raise RuntimeError("ANTHROPIC_API_KEY is not set")

    path, news, title = run(client or NoClient(), model, tickers, args.force_latest)
    print(f"\n{title}\nDigest written to {path}")

    # For the GitHub Actions workflow: whether to open an issue, and with what.
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as out:
            out.write(f"news={'true' if news else 'false'}\n")
            out.write(f"digest={path}\n")
            out.write(f"title={title}\n")


if __name__ == "__main__":
    main()
