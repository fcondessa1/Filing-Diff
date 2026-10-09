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


SUCCESSOR_FLOOR = 0.40   # containment; see not_repeated()


def is_updates_only(text: str) -> bool:
    """
    A section that lists only what changed and says the rest still stands:
    "Other than the risk factors listed below, there have been no material
    changes from the risk factors previously described..." (NVDA, IONQ),
    "Except as set forth below..." (LEU, QBTS), "Below are material changes to
    our risk factors since our Annual Report..." (GOOGL). Read from the
    section's opening, where every filer seen so far puts it.
    """
    opening = text[:800].lower()
    return "below" in opening and re.search(r"material changes?", opening) is not None


# NVIDIA's August opening names both the 10-K and the May 10-Q as still
# standing. A filer naming only the 10-K leaves the earlier 10-Q's updates
# unaddressed, and the digest says so rather than guessing.


def not_repeated(change: dict) -> bool:
    """
    A paragraph missing from an updates-only section with no successor in it.

    Hand verification of NVIDIA's August 2026 10-Q: all 15 "removals" were
    risks updated in May and not updated again in August. The August section
    opens by saying everything else in the 10-K and the May 10-Q still stands,
    so none was dropped. One had been rewritten: the new H20 export-licence
    paragraph keeps its opening sentence and drops the expected 15% revenue
    share. It is the only one whose closest new paragraph holds a large share
    of it (containment 0.46; the next highest of the 15 was 0.33). A removal
    with a successor at or above SUCCESSOR_FLOOR is still judged by the model;
    the rest are reported as not repeated. The floor is set from that one
    filing and should be checked as more are verified.
    """
    best = max((c["containment"] for c in change.get("candidates") or []), default=0.0)
    return change["kind"] == "removed" and best < SUCCESSOR_FLOOR


def process_filing(client, model: str, filing: dict, previous: dict | None,
                   company: str | None = None) -> dict:
    """
    Compare one new filing with its predecessor and summarise the changes.

    10-Q Item 1A sections come in three shapes, seen on the first live runs:
      - full risk factors every quarter (AMZN)
      - one sentence: no material changes since the 10-K (OKTA; IONQ and QBTS
        in Q1)
      - only the updates: "Other than as set forth below, there have been no
        material changes", then the updated risks (NVDA, GOOGL, LEU; IONQ and
        QBTS in Q2)
    A statement is reported as such, not diffed. When the previous 10-Q was a
    statement, everything in an updates section is new since last quarter, so
    it is compared against nothing and every paragraph is reported as added.
    When the new section lists only updates, a paragraph it leaves out was not
    updated again, not dropped: see not_repeated().
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
        note = (f"The previous {previous['form']} ({nice_date(previous['filing_date'])}) reported "
                f"no changes to its risk factors, so every risk listed here is new since then.")

    changes, skipped = collect_changes(join_fragments(old_text), join_fragments(new_text))
    left_out = []
    if old_text and is_updates_only(new_text):
        left_out = [c["old"] for c in changes if not_repeated(c)]
        changes = [c for c in changes if not not_repeated(c)]
    if company:
        changes = [{**c, "company": company} for c in changes]
    rows = [summarise_change(client, model, c) for c in changes]
    if not rows and not note:
        note = "No changes to Risk Factors."
    return {**base, "rows": rows, "skipped": skipped, "not_repeated": left_out, "note": note,
            "cites_previous_10q": re.search(r"quarterly report|form 10-q",
                                            new_text[:800], re.IGNORECASE) is not None}


# --------------------------------------------------------------------------- #
# Writing the digest
# --------------------------------------------------------------------------- #

def first_sentence(text: str, limit: int = 140) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    m = _INNER_SENTENCE_BREAK.search(text)
    head = text[:m.start() + 1] if m else text
    return head if len(head) <= limit else head[:limit].rsplit(" ", 1)[0] + "…"


# --------------------------------------------------------------------------- #
# A headline per company
# --------------------------------------------------------------------------- #

HEADLINE_PROMPT = """You write the headline for one company's row in a weekly digest of changes to companies' Risk Factors, read by an individual investor.

You get the changes found in the company's latest filing, each already summarised and checked against the filing. Use only these summaries.

Write one headline of at most 12 words naming the main theme, or, if there is none, the most important change.
- Sentence case: capitalise only the first word and proper names. Good: "SkyWater acquisition brings foundry and integration risks". Bad: "SkyWater Acquisition Brings Foundry And Integration Risks".
- Do not name the company or its ticker; the table already shows it.
- Use only facts and figures that appear in the summaries. Do not reinterpret them (for example, a share sale is not a buyback).
- Say "removed" only for changes listed as REMOVED or PARTLY REMOVED. Keep "could" and "may": these are risks, not events."""

HEADLINE_SCHEMA = {
    "type": "object",
    "properties": {"headline": {"type": "string"}},
    "required": ["headline"],
    "additionalProperties": False,
}

_NUMBER = re.compile(r"\d[\d,.]*")


def headline_problem(headline: str, ticker: str, summaries: str) -> str | None:
    """
    Checks that can be made in code. A headline is not quoted from the
    filing, so it cannot be verified like the summaries; what can be checked
    is that it adds no figures of its own and follows the style rules.
    A failed check replaces the headline with plain counts.
    """
    for n in _NUMBER.findall(headline):
        n = n.rstrip(".,")
        if n and n not in summaries:
            return f"number {n} is not in the summaries"
    if re.search(rf"\b{re.escape(ticker)}\b", headline, re.IGNORECASE):
        return "names the ticker"
    if len(headline.split()) > 16:
        return "too long"
    return None


def add_headline(client, model: str, ticker: str, result: dict) -> None:
    """
    A short headline for the company's row in the summary table, written
    from the checked summaries.

    Earlier versions also wrote a one- or two-sentence story under each
    company. On the 9 October 2026 run the Alphabet story called a $40
    billion at-the-market share sale a "share buyback", the opposite, while
    the checked summaries beneath it had it right. Nothing checks text the
    model writes from summaries, so the stories were dropped; the headline
    stays because it is short, and code checks it adds no numbers of its own.
    Cached like the summaries. On any failure the table shows counts instead.
    """
    import hashlib
    from summarise import CACHE_DIR, ORDER, response_json, row_label

    rows = sorted(result["rows"], key=lambda r: ORDER.get(r["materiality"], 3))
    rows = [r for r in rows if r["materiality"] in ("high", "medium")] or rows
    if not rows:
        return
    listing = "\n".join(f"- [{r['materiality'].upper()}] {row_label(r)}: {r['summary']}"
                         for r in rows[:25])
    message = f"FILING: {result['filing']['form']}\n\nCHANGES:\n{listing}"
    key = hashlib.sha256(json.dumps(["headline-v2", model, message]).encode()).hexdigest()[:24]
    path = CACHE_DIR / f"headline_{key}.json"
    try:
        if path.exists():
            parsed = json.loads(path.read_text())
        else:
            response = client.messages.create(
                model=model, max_tokens=200, system=HEADLINE_PROMPT,
                messages=[{"role": "user", "content": message}],
                output_config={"format": {"type": "json_schema", "schema": HEADLINE_SCHEMA}})
            parsed = response_json(response)
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(parsed))
        headline = (parsed.get("headline") or "").strip().rstrip(".")
        problem = headline_problem(headline, ticker, listing) if headline else "empty"
        if problem:
            print(f"{ticker}: headline dropped ({problem}): {headline!r}")
        else:
            result["headline"] = headline
    except Exception as e:  # the headline is a convenience; never fail the digest over it
        print(f"{ticker}: no headline ({type(e).__name__}: {e})")


# --------------------------------------------------------------------------- #
# Writing the digest
# --------------------------------------------------------------------------- #

KIND_LABEL = {"added": "New", "modified": "Changed"}
VERDICT_SHORT = {"removed": "Removed", "partially_removed": "Partly removed",
                 "moved_or_reworded": "Reworded"}
_BOILERPLATE = re.compile(
    r"^(the )?company (has )?(added|disclosed|introduced)\s+"
    r"(an? )?(new )?(specific )?(risk factor|risk disclosure|disclosure|risk|language)?s?\s*"
    r"(regarding|about|on|concerning|addressing|related to|disclosing|describing|"
    r"highlighting|detailing|that|of)?\s*(that\s+)?", re.IGNORECASE)


def short_summary(text: str) -> str:
    """Drop the "The company added a new risk factor regarding" opening the
    label already says, and keep the rest."""
    cut = _BOILERPLATE.sub("", text.strip(), count=1)
    if len(cut) < 25:
        return text
    return cut[0].upper() + cut[1:]


def nice_date(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b %Y')}"


def change_label(r: dict) -> str:
    if r["kind"] == "removed":
        return VERDICT_SHORT.get(r.get("verdict"), "Removed")
    return KIND_LABEL.get(r["kind"], r["kind"].title())


def change_line(r: dict) -> str:
    flags = []
    if r["check"]["status"] != "VERIFIED":
        flags.append("quote not found in filing" if r["check"]["status"] == "UNSUPPORTED"
                     else "one quote not found in filing")
    if r["check"].get("verdict_supported") is False:
        flags.append("verdict not supported by a quote")
    warn = f" ⚠️ _{'; '.join(flags)}_" if flags else ""
    return f"- **{change_label(r)}** · {short_summary(r['summary'])}{warn}"


def counts(result: dict) -> dict:
    rows = result["rows"]
    return {lvl: sum(r["materiality"] == lvl for r in rows) for lvl in ("high", "medium", "low")}


LEVELS = [("high", "🔴 High importance"), ("medium", "🟡 Medium importance"),
          ("low", "⚪ Low importance")]


def at_a_glance(ticker: str, result: dict) -> str:
    f = result["filing"]
    c = counts(result)
    if result.get("extraction_failed"):
        what = "⚠️ Could not read Risk Factors"
    elif result.get("headline"):
        what = result["headline"]
    elif result["rows"]:
        n = len(result["rows"])
        what = f"{n} change{'s' if n > 1 else ''}"
    elif result.get("not_repeated"):
        what = "Nothing new; some earlier updates not repeated"
    else:
        what = "No changes"
    nums = " | ".join(str(c[lvl]) if result["rows"] else "–" for lvl, _ in LEVELS)
    return (f"| **{ticker}** | {f['form']}, {nice_date(f['filing_date'])} | {what} | {nums} |")


def company_heading(ticker: str, result: dict) -> str:
    """Links to both filings, so any change can be checked against the
    original on either side."""
    f, prev = result["filing"], result["previous"]
    vs = (f" · compared with [{prev['form']} of {nice_date(prev['filing_date'])}]({prev['url']})"
          if prev else "")
    return f"### {ticker} · [{f['form']} of {nice_date(f['filing_date'])}]({f['url']}){vs}"


def importance_section(level: str, title: str, processed: list[tuple[str, dict]]) -> list[str]:
    """Every company's changes at one importance level, grouped by company."""
    from summarise import ORDER

    groups = [(t, r, [x for x in r["rows"] if x["materiality"] == level]) for t, r in processed]
    groups = [(t, r, rows) for t, r, rows in groups if rows]
    if not groups:
        return []
    total = sum(len(rows) for _, _, rows in groups)
    lines = [f"## {title} ({total})", ""]
    if level == "low":
        # Wording changes: counts only, the text is in the JSON.
        lines += [", ".join(f"**{t}** {len(rows)}" for t, _, rows in groups)
                  + ". Minor wording changes; listed in the JSON file next to this digest.", ""]
        return lines
    for t, r, rows in groups:
        # A company's filing links and note go with its most important
        # changes. Below that level its changes are folded under its name, so
        # the medium section reads as a list of companies to open.
        top = next(lvl for lvl, _ in LEVELS if any(x["materiality"] == lvl for x in r["rows"]))
        if level == top:
            lines += [company_heading(t, r), ""]
            if r["note"]:
                lines += [r["note"], ""]
            lines += [change_line(x) for x in rows] + [""]
        else:
            lines += [f"<details><summary><b>{t}</b> · {len(rows)} change"
                      f"{'s' if len(rows) > 1 else ''}</summary>", ""]
            lines += [change_line(x) for x in rows] + ["", "</details>", ""]
    return lines


def nothing_new_section(processed: list[tuple[str, dict]]) -> list[str]:
    """Filings with no changes, failed extractions, and risks not repeated."""
    lines = []
    for t, r in processed:
        only_low = r["rows"] and all(x["materiality"] == "low" for x in r["rows"])
        if (not r["rows"] or only_low) and (r["note"] or r.get("extraction_failed")):
            lines += [company_heading(t, r), "", r["note"] or "", ""]
    for t, r in processed:
        left_out = r.get("not_repeated") or []
        if not left_out:
            continue
        if r.get("cites_previous_10q"):
            why = ("The filing lists only updates and says everything in the 10-K and earlier "
                   "10-Qs still stands, so these were not updated again, not removed.")
        else:
            why = ("The filing lists only updates since the 10-K and does not say whether the "
                   "previous 10-Q's updates still stand. Most likely they were not updated "
                   "again rather than removed; check the filing if one matters to you.")
        lines += [f"<details><summary><b>{t}</b>: {len(left_out)} risks from the previous "
                  f"{r['previous']['form']} not repeated (still stand)</summary>", "", why, ""]
        lines += [f"- {first_sentence(x)}" for x in left_out] + ["", "</details>", ""]
    return (["## No changes and other notes", ""] + lines) if lines else []


def run_details(processed: list[tuple[str, dict]], model: str) -> list[str]:
    from summarise import cost_usd

    lines = ["<details><summary>Run details</summary>", "",
             "| Company | Changes (high / medium / low) | Quotes verified | Merges skipped | Cost |",
             "|---|---|---|---|---|"]
    total = 0.0
    for t, r in processed:
        rows = r["rows"]
        if not rows:
            continue
        c = counts(r)
        verified = sum(x["check"]["status"] == "VERIFIED" for x in rows)
        cost = cost_usd(model, sum(x["input_tokens"] for x in rows),
                        sum(x["output_tokens"] for x in rows)) or 0.0
        total += cost
        lines.append(f"| {t} | {len(rows)} ({c['high']} / {c['medium']} / {c['low']}) "
                     f"| {verified} of {len(rows)} | {len(r.get('skipped') or [])} | ${cost:.3f} |")
    lines += ["", f"Model `{model}`. Summaries cost ${total:.2f} in total (the headlines add "
              f"a little). Every summary quotes the filing and the quotes are checked; a ⚠️ "
              f"marks a summary whose quote was not found. Table headlines are written "
              f"from the checked summaries and are not themselves checked against the filing. Full detail is in the JSON file next to this digest.",
              "", "</details>", ""]
    return lines


def write_digest(date: str, results: dict[str, list[dict]], errors: dict[str, str],
                 baselines: list[str], model: str) -> tuple[Path, bool, str]:
    """Returns the digest path, whether there is news, and an issue title."""
    processed = [(t, r) for t, rs in results.items() for r in rs]
    news = bool(processed or errors)
    lines = [f"# Filing digest, {nice_date(date)}", ""]

    if not news:
        lines.append("No new 10-K or 10-Q filings this week.")
    if processed:
        n_high = sum(counts(r)["high"] for _, r in processed)
        quiet = sum(not r["rows"] for _, r in processed)
        summary = (f"{len(processed)} new filing{'s' if len(processed) > 1 else ''} · "
                   f"{n_high} high-importance change{'s' if n_high != 1 else ''}"
                   + (f" · {quiet} with nothing new" if quiet else ""))
        lines += [f"**{summary}**", "",
                  "| Company | Filing | What changed | 🔴 High | 🟡 Medium | ⚪ Low |",
                  "|---|---|---|---|---|---|"]
        lines += [at_a_glance(t, r) for t, r in processed] + [""]
    if errors:
        lines += ["⚠️ **Errors** (these filings will be retried next week):", ""]
        lines += [f"- **{t}**: {msg}" for t, msg in errors.items()] + [""]
    if baselines:
        lines += [f"_First run for {', '.join(baselines)}: latest filings recorded as the "
                  f"starting point. Changes are reported from the next filing on._", ""]
    for level, title in LEVELS:
        section = importance_section(level, title, processed)
        if section:
            lines += ["---", ""] + section
    notes = nothing_new_section(processed)
    if notes:
        lines += ["---", ""] + notes
    if any(r["rows"] for _, r in processed):
        lines += ["---", ""] + run_details(processed, model)

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
            if result["rows"]:
                add_headline(client, model, ticker, result)
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
