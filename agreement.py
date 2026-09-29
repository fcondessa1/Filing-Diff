"""
Do two metrics agree on the actual classification, or only on the counts?

The AAPL sweep produced identical buckets (4 added / 13 removed / 46 modified)
for token@0.25 and idf@0.12. That is suggestive but not conclusive: the same
counts can come from different partitions. This checks set membership.

Agreement between metrics that fail in different ways is the closest thing to
ground truth available without hand-labelling every paragraph. Disagreements
are the paragraphs worth reading by hand -- they are where the choice of metric
changes the answer an investor sees.

Two shapes of disagreement, and they mean different things:

  FLOOR disagreements -- one metric says modified, the other says added or
  removed. The metrics disagree about whether two paragraphs are the same
  paragraph at all. When these form a SWAP (metric A calls X modified and Y
  added while metric B says the reverse) neither metric is wrong and the bug is
  upstream; that is how the min_chars boundary bug was found. See boundary.py.

  CEILING disagreements -- one metric says modified, the other says unchanged.
  Both agree the paragraphs are a pair; they disagree about whether the edit is
  material or cosmetic. These are the more interesting ones to read, because a
  metric that calls a real edit cosmetic is hiding information.

An earlier version of this script only read the added/removed/modified buckets,
so pairs scoring above MODIFIED_CEILING appeared in none of them and were
misreported as "unmatched". diff2.diff_sections now returns them explicitly.

Usage:
    python agreement.py AAPL 1A
"""

import sys

from diff2 import diff_sections
from run_diff import load_pair

KEY_CHARS = 120  # enough of a paragraph to identify it uniquely


def classify(result: dict) -> dict[str, str]:
    """
    Map each paragraph's opening characters to its bucket.

    Every paragraph in both filings lands in exactly one of the four buckets,
    so a key missing from one metric's map is a bug in this function, not a
    property of the diff.
    """
    out = {}
    for p in result["added"]:
        out[p[:KEY_CHARS]] = "added"
    for p in result["removed"]:
        out[p[:KEY_CHARS]] = "removed"
    for label in ("modified", "unchanged"):
        for m in result[label]:
            out[m["new"][:KEY_CHARS]] = label
            out[m["old"][:KEY_CHARS]] = label
    return out


def compare(old_text, new_text, a=("token", 0.25), b=("idf", 0.12)):
    ra = diff_sections(old_text, new_text, metric=a[0], floor=a[1])
    rb = diff_sections(old_text, new_text, metric=b[0], floor=b[1])

    for (metric, floor), r in ((a, ra), (b, rb)):
        s = r["stats"]
        print(f"{metric}@{floor}: {s['added']} added, {s['removed']} removed, "
              f"{s['modified']} modified, {s['unchanged']} unchanged")
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

    ceiling_pair = {"modified", "unchanged"}
    floor_cases, ceiling_cases = [], []
    for k in disagree:
        verdicts = {ca.get(k, "MISSING"), cb.get(k, "MISSING")}
        (ceiling_cases if verdicts == ceiling_pair else floor_cases).append(k)

    def show(title, keys, note):
        if not keys:
            return
        print(f"=== {title} ({len(keys)}) ===")
        print(note + "\n")
        for k in keys:
            print(f"  {a[0]}={ca.get(k, 'MISSING'):<10} {b[0]}={cb.get(k, 'MISSING')}")
            print(f"  {k}...\n")

    show("FLOOR disagreements", floor_cases,
         "The metrics disagree about whether these are the same paragraph.\n"
         "If two form a swap, suspect the length filter rather than either\n"
         "metric, and run boundary.py.")
    show("CEILING disagreements", ceiling_cases,
         "Both metrics paired these; they disagree about whether the edit is\n"
         "material or cosmetic. Read the pair and decide which is right --\n"
         "a metric calling a real edit cosmetic is hiding information.")

    if any(v == "MISSING" for v in list(ca.values()) + list(cb.values())):
        print("MISSING means classify() lost a paragraph -- that is a bug here,")
        print("not a property of the diff.\n")


def main():
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    item = sys.argv[2] if len(sys.argv) > 2 else "1A"

    old_text, new_text = load_pair(ticker, item)
    print()
    compare(old_text, new_text)


if __name__ == "__main__":
    main()
