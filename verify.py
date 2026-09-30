"""
Check whether each REMOVED paragraph really disappeared, or survived inside a
paragraph the diff could not pair with it.

Why this exists. Hungarian assignment is a bijection: one old paragraph pairs
with at most one new paragraph. A filer merging three paragraphs into one has
no representable form, so one old paragraph wins the pairing and the others fall
out as REMOVED even though their content survives verbatim. Found by hand on
AAPL FY2025, where Apple consolidated several competition paragraphs into one:
the merge produced a phantom ADDED entry and several phantom REMOVED entries at
the same time.

Jaccard cannot detect this. It is symmetric, so a short paragraph absorbed into
a much longer one scores low purely on the size difference -- the union grows
while the intersection does not. CONTAINMENT is the right measure:

    containment(old, new) = shared IDF mass / old's IDF mass

That asks "how much of the old paragraph still exists in this new one?" and
ignores whatever else the new paragraph gained.

This script does the searching. The verdicts are labelled LIKELY because the
judgment is still yours -- read the pairs it prints and decide.

Usage:
    python verify.py AAPL 1A
    python verify.py AAPL 1A > verification.txt
"""

import sys

from diff2 import diff_sections, split_paragraphs
from idf import build_idf, tokens
from run_diff import load_pair

# How much of the old paragraph must survive before we call it "still present".
CONTAINMENT_FLOOR = 0.55

# How much longer the host paragraph must be before absorption is the better
# explanation than a plain missed pairing.
GROWTH_RATIO = 1.25


def containment(old: str, new: str, idf: dict[str, float]) -> float:
    """
    Weighted asymmetric containment: what fraction of old's information mass
    appears in new. Unlike Jaccard, unaffected by how much else new contains.
    """
    told, tnew = set(tokens(old)), set(tokens(new))
    if not told:
        return 0.0
    mass_shared = sum(idf.get(t, 1.0) for t in told & tnew)
    mass_old = sum(idf.get(t, 1.0) for t in told)
    return mass_shared / mass_old if mass_old else 0.0


def classify(removed: str, host: str, score: float, host_is_taken: bool) -> str:
    """
    Three explanations for a REMOVED paragraph, in decreasing order of
    interest to an investor.
    """
    if score < CONTAINMENT_FLOOR:
        return "LIKELY REAL REMOVAL"
    if len(host) > len(removed) * GROWTH_RATIO or host_is_taken:
        return "LIKELY MERGE ARTIFACT"
    return "LIKELY MATCHER MISS"


def verify(old_text: str, new_text: str, metric: str = "idf"):
    result = diff_sections(old_text, new_text, metric=metric)
    new_paras = split_paragraphs(new_text)
    idf = build_idf(split_paragraphs(old_text) + new_paras)

    # New paragraphs the diff already paired with some old paragraph. If a
    # removed paragraph's best host is one of these, that host is serving two
    # old paragraphs at once -- which is a merge by definition.
    taken = {m["new"] for m in result["modified"]} | {m["new"] for m in result["unchanged"]}

    findings = []
    for removed in result["removed"]:
        best_host, best_score = max(
            ((h, containment(removed, h, idf)) for h in new_paras),
            key=lambda x: x[1],
            default=("", 0.0),
        )
        verdict = classify(removed, best_host, best_score, best_host in taken)
        findings.append({
            "removed": removed,
            "host": best_host,
            "containment": best_score,
            "host_taken": best_host in taken,
            "verdict": verdict,
        })

    findings.sort(key=lambda f: -f["containment"])
    return result, findings


def report(result: dict, findings: list[dict], excerpt: int | None = None):
    """
    excerpt=None prints paragraphs in full. That is the default because this
    output is meant to be read against the source filing and verdicts written
    into it -- a truncated paragraph cannot be judged. Pass an int only when
    skimming on screen.
    """
    def show_text(text: str) -> str:
        return text if excerpt is None else text[:excerpt]

    s = result["stats"]
    print(f"diff: {s['added']} added, {s['removed']} removed, "
          f"{s['modified']} modified, {s['unchanged']} unchanged\n")

    tally: dict[str, int] = {}
    for f in findings:
        tally[f["verdict"]] = tally.get(f["verdict"], 0) + 1

    print("=== tally of flagged removals ===")
    for verdict in ("LIKELY REAL REMOVAL", "LIKELY MERGE ARTIFACT", "LIKELY MATCHER MISS"):
        print(f"  {verdict:<24} {tally.get(verdict, 0)}")
    real = tally.get("LIKELY REAL REMOVAL", 0)
    total = len(findings)
    if total:
        print(f"\n  {real}/{total} removals survive as genuine "
              f"({100 * real / total:.0f}%)")
    print()

    for i, f in enumerate(findings, 1):
        print(f"--- {i}. {f['verdict']}  (containment={f['containment']:.3f}"
              f"{', host already paired' if f['host_taken'] else ''}) ---")
        print(f"REMOVED ({len(f['removed'])} chars):\n  {show_text(f['removed'])}\n")
        if f["containment"] >= CONTAINMENT_FLOOR:
            growth = len(f["host"]) / max(len(f["removed"]), 1)
            print(f"BEST HOST IN NEW FILING ({len(f['host'])} chars, "
                  f"{growth:.1f}x longer):\n  {show_text(f['host'])}\n")
        else:
            print(f"CLOSEST TEXT IN NEW FILING (containment only "
                  f"{f['containment']:.3f} -- probably not the same risk, "
                  f"but read it before calling this a removal):\n"
                  f"  {show_text(f['host'])}\n")
        print("  your verdict: ______________________\n")

    print("Read each pair and overrule the label where it is wrong. The tally")
    print("is the result worth reporting -- a removal count alone is not")
    print("trustworthy while merges are invisible to the matcher.")


def main():
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    item = sys.argv[2] if len(sys.argv) > 2 else "1A"

    old_text, new_text = load_pair(ticker, item)
    print()
    report(*verify(old_text, new_text))


if __name__ == "__main__":
    main()
