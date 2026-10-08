"""
Why did Risk Factors extraction fail for a filing?

The first multi-company digest found no Risk Factors section in four 10-Qs
(IONQ, OKTA, AMZN, QBTS). Those companies normally repeat their full risk
factors every quarter, so "no material changes" is unlikely: the extractor
(tuned on Apple's filings) probably missed the heading. This prints, for each
filing, what the extractor saw, so the fix is based on evidence, not guesses.

For each filing:
  - extracted length (or FAILED)
  - headings the extractor accepted, and the span each would give
  - every "Item 1A" in the document, with whether it sits inside a <table>
    (sections.py drops tables, so a heading inside one is invisible), whether
    it starts a line, and the text around it

Usage:
    python diagnose_extraction.py                 # the four failing tickers
    python diagnose_extraction.py AMZN OKTA --n 4
"""

import argparse
import re

from bs4 import BeautifulSoup

from edgar import fetch_document, get_cik, list_filings
from sections import BOUNDARIES, _find_all, extract_item, html_to_text

ITEM_1A = re.compile(r"item\s*1a\b", re.IGNORECASE)


def text_keeping_tables(html: str) -> tuple[str, list[str]]:
    """The same flattening as sections.html_to_text, but tables are kept, and
    the text of every table that mentions Item 1A is returned separately."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    in_tables = []
    for t in soup.find_all("table"):
        label = re.sub(r"\s+", " ", t.get_text(" ").replace("\xa0", " ")).strip()
        if ITEM_1A.search(label):
            if len(label) < 120:   # a heading table: show its structure
                rows = len(t.find_all("tr"))
                filled = sum(1 for tr in t.find_all("tr") if tr.get_text(strip=True))
                label += f"  [rows: {rows}, with text: {filled}; html: {str(t)[:300]}]"
            in_tables.append(label)
    for tag in soup.find_all(["p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"]):
        tag.insert_after(soup.new_string("\n\n"))
    text = soup.get_text(separator="\n").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text, in_tables


def diagnose(filing: dict) -> None:
    html = fetch_document(filing["url"])
    text = html_to_text(html)
    body = extract_item(text, "1A")
    status = f"{len(body):,} chars" if body else "FAILED"
    print(f"\n=== {filing['form']} filed {filing['filing_date']}: {status}")
    print(f"    {filing['url']}")
    short = None if body else extract_item(text, "1A", min_chars=100)
    if short:
        # Short sections: is it a "no changes" statement, or a section cut
        # off early by a false end marker? Show it and what comes after.
        at = text.find(short)
        print(f"  short section ({len(short)} chars):\n    {short!r}")
        print(f"  next 300 chars:\n    {text[at + len(short):at + len(short) + 300]!r}")

    # What the extractor saw (tables dropped).
    starts = _find_all(text, "1A")
    ends = sorted(e for t in BOUNDARIES["1A"] for e in _find_all(text, t.replace("item ", "")))
    print(f"  extractor: {len(starts)} heading(s) accepted, {len(ends)} end marker(s)")
    for s in starts:
        stop = min([e for e in ends if e > s], default=len(text))
        snippet = text[s:s + 70].replace("\n", " | ")
        print(f"    start {s:>7,} -> span {stop - s:>7,} chars: {snippet!r}")

    # Every mention in the full document, tables included.
    full, tables = text_keeping_tables(html)
    print(f"  tables mentioning Item 1A: {len(tables)}")
    for t in tables[:3]:
        print(f"    table: {t[:110] if 'rows:' not in t else t!r}")
    mentions = list(ITEM_1A.finditer(full))
    print(f"  'Item 1A' anywhere (tables kept): {len(mentions)}")
    for m in mentions[:8]:
        line_start = full.rfind("\n", 0, m.start()) + 1
        at_start = full[line_start:m.start()].strip() == ""
        context = full[max(0, m.start() - 40):m.end() + 70].replace("\n", " | ")
        print(f"    {'line-start' if at_start else 'mid-line  '} {context!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*", default=["IONQ", "OKTA", "AMZN", "QBTS"])
    ap.add_argument("--n", type=int, default=2, help="recent 10-Qs per ticker")
    args = ap.parse_args()
    for ticker in args.tickers:
        print(f"\n################ {ticker}")
        for filing in list_filings(get_cik(ticker), form_types=("10-Q",), limit=args.n):
            try:
                diagnose(filing)
            except Exception as e:
                print(f"  error: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
