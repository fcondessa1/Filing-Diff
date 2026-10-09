"""
How much does joining headlines (digest.join_fragments) change the diff?

For each ticker's latest filing and the previous filing of the same form,
counts the changes the digest would summarise with and without joining, and
shows a few joined headlines so you can check they were joined to the right
body. Makes no API calls: it stops before the model.

Usage:
    python check_joining.py              # every ticker in watchlist.txt
    python check_joining.py IONQ GOOGL
"""

import argparse
import re
from collections import Counter

import digest
from edgar import get_cik, list_filings
from summarise import collect_changes


def count(old: str, new: str) -> Counter:
    changes, _ = collect_changes(old, new)
    return Counter(c["kind"] for c in changes)


def show(counter: Counter) -> str:
    return (f"{sum(counter.values()):>3} changes "
            f"({counter['added']} added, {counter['removed']} removed, {counter['modified']} modified)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*")
    args = ap.parse_args()
    tickers = args.tickers or digest.load_watchlist()

    total_before = total_after = 0
    for ticker in tickers:
        filings = list_filings(get_cik(ticker), form_types=("10-K", "10-Q"), limit=digest.LOOKBACK)
        latest = filings[0]
        previous = digest.previous_of_same_form(filings, latest)
        print(f"\n=== {ticker} {latest['form']} {latest['filing_date']} vs "
              f"{previous['filing_date'] if previous else 'nothing'}")
        if previous is None:
            continue
        new, old = digest.risk_factors(latest["url"]), digest.risk_factors(previous["url"])
        if not new or not old:
            print("  extraction failed")
            continue
        if digest.is_statement(new):
            print("  'no changes' statement: nothing to summarise")
            continue
        if digest.is_statement(old):
            old = ""

        before, after = count(old, new), count(digest.join_fragments(old), digest.join_fragments(new))
        total_before += sum(before.values())
        total_after += sum(after.values())
        print(f"  without joining: {show(before)}")
        print(f"  with joining:    {show(after)}")

        # Show a few joins: the headline, then the start of the body it got.
        joins = [p for p in digest.join_fragments(new).split("\n\n")
                 if p not in new.split("\n\n")]
        for p in joins[:3]:
            m = re.search(r"[.!?][\"”’)]*\s+(?=[A-Z])", p)
            head, body = (p[:m.end()], p[m.end():]) if m else (p, "")
            print(f"    HEADLINE: {head.strip()[:120]!r}")
            print(f"    BODY:     {body.strip()[:120]!r}")

    if total_before:
        print(f"\nTotal: {total_before} changes without joining, {total_after} with "
              f"({1 - total_after / total_before:.0%} fewer).")


if __name__ == "__main__":
    main()
