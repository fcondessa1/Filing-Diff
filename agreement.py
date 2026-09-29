"""
Do two metrics agree on the actual classification, or only on the counts?

The AAPL sweep produced identical buckets (4 added / 13 removed / 46 modified)
for token@0.25 and idf@0.12. That is suggestive but not conclusive: the same
counts can come from different partitions. This checks set membership.

Agreement between metrics that fail in different ways is the closest thing to
ground truth available without hand-labelling every paragraph. Disagreements
are the paragraphs worth reading by hand -- they are where the choice of metric
changes the answer an investor sees.

A disagreement that is a SWAP (metric A calls X modified and Y added while
metric B says the reverse) usually means neither metric is wrong and the bug is
upstream. That is how the min_chars boundary bug was found; see boundary.py.

Usage:
    python agreement.py AAPL 1A
"""

import sys

from diff2 import diff_sections
from run_diff import load_pair

KEY_CHARS = 120  # enough of a paragraph to identify it uniquely


def classify(result: dict) -> dict[str, str]:
    """Map each paragraph's opening characters to its bucket."""
    out = {}
    for p in result["added"]:
        out[p[:KEY_CHARS]] = "added"
    for p in result["removed"]:
        out[p[:KEY_CHARS]] = "removed"
    for m in result["modified"]:
        out[m["new"][:KEY_CHARS]] = "modified"
        out[m["old"][:KEY_CHARS]] = "modified"
    return out


def compare(old_text, new_text, a=("token", 0.25), b=("idf", 0.12)):
    ra = diff_sections(old_text, new_text, metric=a[0], floor=a[1])
    rb = diff_sections(old_text, new_text, metric=b[0], floor=b[1])

    for (metric, floor), r in ((a, ra), (b, rb)):
        s = r["stats"]
        print(f"{metric}@{floor}: {s['added']} added, "
              f"{s['removed']} removed, {s['modified']} modified")
    print()

    ca, cb = classify(ra), classify(rb)
    keys = set(ca) | set(cb)

    disagree = [k for k in keys if ca.get(k) != cb.get(k)]
    agreed = len(keys) - len(disagree)
    pct = 100 * agreed / len(keys) if keys else 0.0
    print(f"agreement: {agreed}/{len(keys)} paragraphs ({pct:.1f}%)\n")

    if not disagree:
        print("Identical partitions -- the two metrics made the same call on")
        print("every paragraph, not merely the same number of calls.\n")
        return

    print("=== disagreements: read these by hand ===\n")
    for k in disagree:
        print(f"  {a[0]}={ca.get(k, 'unmatched'):<9} {b[0]}={cb.get(k, 'unmatched')}")
        print(f"  {k}...\n")
    print("If two of these form a swap, suspect the length filter rather than")
    print("either metric, and run boundary.py.\n")


def main():
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    item = sys.argv[2] if len(sys.argv) > 2 else "1A"

    old_text, new_text = load_pair(ticker, item)
    print()
    compare(old_text, new_text)


if __name__ == "__main__":
    main()
