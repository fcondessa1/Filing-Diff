"""
Diff behaviour across all three metrics, on synthetic paragraphs that reproduce
the failure modes found in real Apple filings.

Run: python test_diff.py
"""

from diff2 import diff_sections, char_similarity, token_similarity
from idf import build_idf, weighted_similarity

FORMULA = "business, results of operations, financial condition and stock price"

OLD = f"""
We face intense competition in all of our markets, which could materially adversely affect our {FORMULA} as competitors introduce comparable products at lower price points.

There can be no assurance that supply chain disruption in Asia will not materially affect our ability to deliver products on schedule, which could materially adversely affect our {FORMULA}.

Our reliance on a single cloud provider exposes us to service interruptions that could materially adversely affect our {FORMULA}.
"""

NEW = f"""
We face intense competition in all of our markets, which could materially adversely affect our {FORMULA} as competitors introduce comparable products at lower price points.

Supply chain disruption in Asia may materially adversely affect our ability to deliver products on schedule, and we expect these constraints to persist, which could materially adversely affect our {FORMULA}.

New artificial intelligence regulation in the European Union may impose compliance obligations that could materially adversely affect our {FORMULA}.
"""


def test_buckets():
    """
    The correct answer: 1 added (EU AI regulation), 1 removed (cloud provider),
    1 modified (supply chain, reworded).

    Heavy boilerplate is deliberate. Plain token overlap force-matches the new
    EU risk onto the removed cloud risk here -- reporting that nothing appeared
    or disappeared -- because the shared formula dominates. IDF weighting
    discounts the formula and gets it right.
    """
    print("=== bucket counts by metric ===")
    print(f"{'metric':>7} {'added':>7} {'removed':>8} {'modified':>9}")
    print("-" * 34)
    for metric in ("char", "token", "idf"):
        s = diff_sections(OLD, NEW, min_chars=120, metric=metric)["stats"]
        print(f"{metric:>7} {s['added']:>7} {s['removed']:>8} {s['modified']:>9}")

    s = diff_sections(OLD, NEW, min_chars=120, metric="idf")["stats"]
    ok = (s["added"], s["removed"], s["modified"]) == (1, 1, 1)
    print(f"\nidf gives the correct 1/1/1 partition: {ok}")
    return ok


def test_classification():
    """The right paragraphs in the right buckets, not just the right counts."""
    r = diff_sections(OLD, NEW, min_chars=120, metric="idf")
    print("\n=== idf classification ===")
    added_ok = "artificial intelligence" in r["added"][0]
    removed_ok = "cloud provider" in r["removed"][0]
    modified_ok = "Supply chain" in r["modified"][0]["new"]
    print(f"ADDED is the EU AI risk     : {added_ok}")
    print(f"REMOVED is the cloud risk   : {removed_ok}")
    print(f"MODIFIED is the supply risk : {modified_ok}")
    return added_ok and removed_ok and modified_ok


def test_rewrite_scores():
    """
    Real pairs from the AAPL output that the character metric wrongly split
    into separate ADDED / REMOVED entries.

    The control pair is two genuinely different risks and must score lowest.
    """
    pairs = [
        ("Additionally, the Company's new products often utilize custom components available from only one source. When a component or product uses new technologies, initial capacity constraints may exist until the suppliers' yields have matured. The Company may not be able to extend or renew agreements for the supply of components on similar terms, or at all.",
         "The Company's new products often utilize custom components available from only one source. When a component or product uses new technologies, initial capacity constraints may exist until the suppliers' yields have matured. The continued availability of these components at acceptable prices, or at all, can be affected for any number of reasons.",
         "same risk, light rewrite"),
        ("The Company believes decisions by customers to purchase its hardware products depend in part on the availability of third-party software applications. Third-party developers may discontinue the development and maintenance of software applications for the Company's products.",
         "The Company believes decisions by customers to purchase its hardware products depend in part on the availability of third-party software applications. There can be no assurance third-party developers will continue to develop and maintain software applications for the Company's products.",
         "'no assurance' stripped"),
        ("The Company has historically experienced higher net sales in its first quarter due in part to seasonal holiday demand.",
         "The Company is also subject to new laws regarding online safety, including enhanced protections for minors and mandatory age verification requirements.",
         "UNRELATED (control)"),
    ]

    corpus = [p for pair in pairs for p in pair[:2]]
    idf = build_idf(corpus)

    print(f"\n=== similarity on real rewrite pairs ===")
    print(f"{'case':<28} {'char':>7} {'token':>7} {'idf':>7}")
    print("-" * 52)
    scores = {}
    for old, new, label in pairs:
        c = char_similarity(old, new)
        t = token_similarity(old, new)
        i = weighted_similarity(old, new, idf)
        scores[label] = (c, t, i)
        print(f"{label:<28} {c:>7.3f} {t:>7.3f} {i:>7.3f}")

    control = scores["UNRELATED (control)"]
    real = [v for k, v in scores.items() if "control" not in k]

    char_ok = all(r[0] > control[0] for r in real)
    token_ok = all(r[1] > control[1] for r in real)
    idf_ok = all(r[2] > control[2] for r in real)
    print(f"\nreal pairs outrank the control -- char: {char_ok}, "
          f"token: {token_ok}, idf: {idf_ok}")
    print("char failing here is the finding, not a broken test.")
    return token_ok and idf_ok


if __name__ == "__main__":
    results = [test_buckets(), test_classification(), test_rewrite_scores()]
    print(f"\n{sum(results)}/{len(results)} checks passed")
