"""
Does containment detect the merge that Jaccard missed?

Reproduces the AAPL competition case: three FY2024 paragraphs consolidated into
one FY2025 paragraph, plus one genuinely dropped paragraph as a control.

Run: python test_verify.py
"""

from diff2 import split_paragraphs, token_similarity
from idf import build_idf
from verify import containment, verify

OLD = """
Additionally, the Company faces significant competition as competitors imitate the Company's product features and applications within their products or collaborate to offer solutions that are more competitive than those they currently offer. The Company also expects competition to intensify as competitors imitate the Company's approach to providing components seamlessly within their offerings.

The Company has a minority market share in the global smartphone, personal computer and tablet markets. Some of the Company's competitors have broad product lines, low-priced products, large installed bases of active devices, and large customer bases.

Competition has been particularly intense as competitors have aggressively cut prices and lowered product margins. Certain competitors have the resources, experience or cost structures to provide products and services at little or no profit or even at a loss.

The Company's retail operations are subject to many factors that pose risks and uncertainties, including macroeconomic factors that could have an adverse effect on general retail activity and the Company's ability to manage store construction costs.
"""

# FY2025: the first three merged into one; the retail paragraph genuinely gone.
NEW = """
The Company is focused on expanding its market opportunities related to smartphones, personal computers, tablets, wearables and accessories, and services. The Company's products and services face substantial competition from companies that have significant technical, marketing, distribution and other resources. In addition, the Company faces significant competition as competitors imitate the Company's product features and applications within their products to offer more competitive solutions. The Company also expects competition to intensify as competitors imitate the Company's approach to providing components seamlessly within their offerings or work collaboratively to offer integrated solutions. Some of the Company's competitors have broad product lines, low-priced products, large installed bases of active devices, and large customer bases. Competition has been particularly intense as competitors have aggressively cut prices and lowered product margins. Certain competitors have the resources, experience or cost structures to provide products and services at little or no profit or even at a loss. The Company has a minority market share in the global smartphone, personal computer, tablet and wearables markets.
"""


def test_metric_contrast():
    """Jaccard is size-sensitive; containment is not."""
    old_paras = split_paragraphs(OLD, 130)
    new_paras = split_paragraphs(NEW, 130)
    idf = build_idf(old_paras + new_paras)
    host = new_paras[0]

    print("=== the same pairs under both measures ===")
    print(f"{'absorbed paragraph':<34} {'jaccard':>9} {'containment':>13}")
    print("-" * 60)
    passing = 0
    for p in old_paras[:3]:
        j = token_similarity(p, host)
        c = containment(p, host, idf)
        label = p[:30].replace("\n", " ")
        print(f"{label:<34} {j:>9.3f} {c:>13.3f}")
        if c > j:
            passing += 1

    control = old_paras[3]
    print(f"{'retail ops (genuinely gone)':<34} "
          f"{token_similarity(control, host):>9.3f} "
          f"{containment(control, host, idf):>13.3f}")
    print(f"\ncontainment exceeds jaccard on all 3 absorbed paragraphs: "
          f"{passing == 3}")
    return passing == 3


def test_verdicts():
    """
    Four old paragraphs, three of them merged into one new paragraph.

    Hungarian assignment gives the merged host to exactly ONE of the three --
    that pair appears in `modified`. The other two have nowhere to go and fall
    out as REMOVED despite surviving verbatim. So the expected tally is 2 merge
    artifacts and 1 real removal, not 3 and 1: the bijection itself is what
    limits how many merges are even visible as removals.
    """
    result, findings = verify(OLD, NEW)

    # The mechanism: one absorbed paragraph won the pairing.
    paired = [m["new"] for m in result["modified"] + result["unchanged"]]
    host_paired = any(len(p) > 900 for p in paired)
    print(f"merged host claimed by one old paragraph: {host_paired}")

    tally: dict[str, int] = {}
    for f in findings:
        tally[f["verdict"]] = tally.get(f["verdict"], 0) + 1

    print("\n=== verdicts ===")
    for f in findings:
        print(f"  {f['verdict']:<24} c={f['containment']:.3f}  "
              f"{f['removed'][:46]}...")

    merges = tally.get("LIKELY MERGE ARTIFACT", 0)
    reals = tally.get("LIKELY REAL REMOVAL", 0)
    print(f"\nmerge artifacts detected: {merges} (expected 2)")
    print(f"real removals detected  : {reals} (expected 1)")
    print("Without containment, all 3 of these would read as removals.")
    return merges == 2 and reals == 1 and host_paired


if __name__ == "__main__":
    results = [test_metric_contrast(), test_verdicts()]
    print(f"\n{sum(results)}/{len(results)} checks passed")
