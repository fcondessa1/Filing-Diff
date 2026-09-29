"""
Tune MATCH_FLOOR against a filing pair you have actually read.

Thresholds picked by intuition are the weakest part of a diff pipeline. This
prints the similarity distribution and the borderline pairs so the number can
be chosen from evidence and defended later.

Usage:
    python tune.py AAPL 1A
"""

import sys

from diff2 import METRICS, build_similarity, diff_sections, split_paragraphs
from run_diff import load_pair

# Scales differ per metric: idf weighting produces much smaller absolute
# values, so a shared floor range would be meaningless.
FLOOR_RANGES = {
    "char": [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60],
    "token": [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60],
    "idf": [0.02, 0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20, 0.30],
}


def sweep(old_text: str, new_text: str, metric: str):
    """How do the buckets move as the floor moves?"""
    print(f"metric = {metric}")
    print(f"{'floor':>6} {'added':>7} {'removed':>8} {'modified':>9}")
    print("-" * 34)
    for floor in FLOOR_RANGES[metric]:
        s = diff_sections(old_text, new_text, metric=metric, floor=floor)["stats"]
        print(f"{floor:>6.2f} {s['added']:>7} {s['removed']:>8} {s['modified']:>9}")
    print()
    print("Read this as: too low and distinct risks get force-matched into")
    print("MODIFIED; too high and rewrites split into a phantom ADD + REMOVE.")
    print("Look for a PLATEAU, then confirm it with the near-miss listing.")
    print()
    print("Beware a degenerate plateau at the bottom of the range: if")
    print("added == 0 and removed == (old_paragraphs - new_paragraphs), every")
    print("new paragraph matched something, which is the maximum possible")
    print("pairing rather than a good one.")
    print()


def near_misses(old_text: str, new_text: str, floor: float, metric: str,
                window: float, limit: int = 8):
    """
    Pairs sitting just below the floor.

    These are the decisions the threshold is actually making. Read them and
    ask: is this the same risk reworded, or two different risks that happen to
    share vocabulary? That judgment is what sets the number.
    """
    old_paras = split_paragraphs(old_text)
    new_paras = split_paragraphs(new_text)
    sim_fn = build_similarity(metric, old_paras + new_paras)

    candidates = []
    for new_p in new_paras:
        best = max(((sim_fn(o, new_p), o) for o in old_paras),
                   key=lambda x: x[0], default=(0.0, ""))
        if floor - window <= best[0] < floor:
            candidates.append((best[0], best[1], new_p))

    candidates.sort(reverse=True, key=lambda x: x[0])
    print(f"=== near misses ({metric}): {floor - window:.2f} <= sim < {floor:.2f} ===\n")
    if not candidates:
        print("(none -- the floor is not sitting on a cluster, which is a good sign)\n")
    for score, old_p, new_p in candidates[:limit]:
        print(f"[sim={score:.3f}]")
        print(f"  OLD: {old_p[:200]}")
        print(f"  NEW: {new_p[:200]}")
        print("  -> same risk reworded, or different risks? ______\n")


def main():
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    item = sys.argv[2] if len(sys.argv) > 2 else "1A"

    old_text, new_text = load_pair(ticker, item)
    print()

    for metric in METRICS:
        sweep(old_text, new_text, metric)

    # Starting guesses on each scale. Replace with the elbow from the sweeps
    # above, then read the pairs the threshold is deciding between.
    near_misses(old_text, new_text, floor=0.25, metric="token", window=0.10)
    near_misses(old_text, new_text, floor=0.12, metric="idf", window=0.05)


if __name__ == "__main__":
    main()
