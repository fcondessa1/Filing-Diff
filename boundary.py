"""
Find paragraphs that min_chars keeps in one filing and drops in the other.

A fixed length filter is not neutral. When a filer adds three words to a
paragraph sitting near the boundary, the old version falls below the cutoff and
the new one clears it. The new paragraph's true counterpart is then absent from
the candidate pool, so the matcher must either call it ADDED or hand it to an
unrelated paragraph -- and different metrics make that forced choice
differently.

This is how the AAPL supply-shortage conclusion was found: token and idf
disagreed on it in opposite directions, which pointed at the filter rather than
at either metric. That paragraph is 197 chars in FY2024 and 210 in FY2025.

Usage:
    python boundary.py AAPL 1A [min_chars]
"""

import re
import sys

from diff2 import MIN_CHARS, split_paragraphs
from idf import build_idf, weighted_similarity
from run_diff import load_pair


def all_paragraphs(text: str) -> list[str]:
    """Every paragraph, unfiltered, so the dropped ones are visible."""
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def find_asymmetric(old_text: str, new_text: str, min_chars: int = MIN_CHARS,
                    band: int = 80, floor: float = 0.30):
    """
    Paragraphs near the cutoff whose counterpart falls on the other side.

    Only pairs that are plausibly the same paragraph are reported -- otherwise
    every short fragment in one filing looks like a finding.
    """
    old_all = all_paragraphs(old_text)
    new_all = all_paragraphs(new_text)
    idf = build_idf(old_all + new_all)

    hits = []
    for label, kept_side, dropped_side in (
        ("kept in NEW, dropped from OLD", new_all, old_all),
        ("kept in OLD, dropped from NEW", old_all, new_all),
    ):
        for kept in kept_side:
            # Only paragraphs near the boundary can be affected by it.
            if not min_chars <= len(kept) <= min_chars + band:
                continue
            for dropped in dropped_side:
                if len(dropped) >= min_chars:
                    continue
                sim = weighted_similarity(kept, dropped, idf)
                if sim >= floor:
                    hits.append((label, sim, len(kept), len(dropped), kept, dropped))

    hits.sort(reverse=True, key=lambda h: h[1])
    return hits


def report(hits, min_chars=MIN_CHARS):
    if not hits:
        print(f"No asymmetric filtering found at min_chars={min_chars}.\n")
        return

    print(f"=== {len(hits)} paragraph(s) filtered asymmetrically at "
          f"min_chars={min_chars} ===\n")
    for label, sim, len_kept, len_dropped, kept, dropped in hits:
        print(f"[{label}]  sim={sim:.3f}  {len_dropped} chars -> {len_kept} chars")
        print(f"  DROPPED ({len_dropped}): {dropped[:220]}")
        print(f"  KEPT    ({len_kept}): {kept[:220]}\n")

    lowest = min(h[3] for h in hits)
    print(f"Lowest dropped counterpart: {lowest} chars.")
    print(f"A cutoff below {lowest} would retain all of these.")
    print("Trade-off: a lower cutoff also readmits headings and page-number")
    print("fragments, which generate their own false diffs. Sweep it below.\n")


def cutoff_table(old_text: str, new_text: str):
    """
    How many paragraphs does each cutoff admit from each filing?

    A cutoff where the two filings gain paragraphs at very different rates is
    one to avoid: the asymmetry is what creates unmatched counterparts.
    """
    print("=== paragraph counts by cutoff ===")
    print(f"{'min_chars':>10} {'old':>6} {'new':>6} {'diff':>6}")
    print("-" * 32)
    for mc in (80, 100, 120, 150, 180, 200, 250):
        o = len(split_paragraphs(old_text, mc))
        n = len(split_paragraphs(new_text, mc))
        print(f"{mc:>10} {o:>6} {n:>6} {o - n:>6}")


def main():
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    item = sys.argv[2] if len(sys.argv) > 2 else "1A"
    min_chars = int(sys.argv[3]) if len(sys.argv) > 3 else MIN_CHARS

    old_text, new_text = load_pair(ticker, item)
    print()
    report(find_asymmetric(old_text, new_text, min_chars=min_chars), min_chars)
    cutoff_table(old_text, new_text)


if __name__ == "__main__":
    main()
