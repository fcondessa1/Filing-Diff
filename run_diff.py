"""
Pull two consecutive filings for a ticker and print what changed.

Usage:
    python run_diff.py AAPL 1A
    python run_diff.py MSFT 7
    python run_diff.py AAPL 1A token     # override the metric
"""

import sys

from edgar import get_cik, list_filings, fetch_document
from sections import extract_sections
from diff2 import diff_sections

# Anything shorter than this is a TOC fragment, not a real section body.
MIN_PLAUSIBLE_SECTION = 5000


def load_pair(ticker: str, item: str, form: str = "10-K"):
    """Fetch and extract one Item from the two most recent filings of a form."""
    cik = get_cik(ticker)
    # 10-Ks are annual and get buried under quarterlies, so look back further.
    filings = list_filings(cik, form_types=(form,), limit=12)
    if len(filings) < 2:
        raise SystemExit(f"Need two {form} filings for {ticker}, found {len(filings)}")

    new_f, old_f = filings[0], filings[1]
    print(f"{ticker} {form} - comparing {old_f['filing_date']} -> {new_f['filing_date']}\n")

    sections = {}
    for label, filing in (("new", new_f), ("old", old_f)):
        extracted = extract_sections(fetch_document(filing["url"]), items=(item,))
        if item not in extracted:
            raise SystemExit(f"FAILED: Item {item} not found in {label} filing")
        sections[label] = extracted[item]
        print(f"{label} Item {item}: {len(extracted[item]):,} chars")

    if min(len(sections["old"]), len(sections["new"])) < MIN_PLAUSIBLE_SECTION:
        print("\nWARNING: suspiciously short - likely a TOC artifact, not the body")

    return sections["old"], sections["new"]


def report(result: dict, excerpt: int = 400):
    print(f"\n{result['stats']}\n")

    for para in result["added"]:
        print(f"[ADDED]\n{para[:excerpt]}\n")
    for para in result["removed"]:
        print(f"[REMOVED]\n{para[:excerpt]}\n")
    for m in result["modified"]:
        print(f"[MODIFIED sim={m['similarity']}]")
        print(f"OLD: {m['old'][:excerpt // 2]}")
        print(f"NEW: {m['new'][:excerpt // 2]}\n")


def main():
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    item = sys.argv[2] if len(sys.argv) > 2 else "1A"
    metric = sys.argv[3] if len(sys.argv) > 3 else "idf"

    old_text, new_text = load_pair(ticker, item)
    report(diff_sections(old_text, new_text, metric=metric))


if __name__ == "__main__":
    main()
