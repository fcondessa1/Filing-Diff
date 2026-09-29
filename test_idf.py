"""
Does IDF weighting fix the score inversion that phrase-stripping could not?

The two intro paragraphs below are recognisably the same paragraph rewritten;
the supply conclusion is a different risk. Plain Jaccard ranks them the wrong
way round because all three end with Apple's stock formula.

Run: python test_idf.py
"""

from diff2 import token_similarity
from idf import build_idf, weighted_similarity

FORMULA = "business, results of operations, financial condition and stock price"

INTRO_OLD = (
    f"The Company's {FORMULA} can be affected by a number of factors, whether "
    "currently known or unknown, including those described below. When any one or "
    f"more of these risks materialize from time to time, the Company's {FORMULA} "
    "can be materially and adversely affected."
)

SUPPLY_NEW = (
    "Therefore, the Company remains subject to significant risks of supply shortages "
    f"and price increases that can materially adversely affect its {FORMULA}."
)

INTRO_NEW = (
    "The following summarizes factors that could have a material adverse effect on "
    f"the Company's {FORMULA}. The Company may not be able to accurately predict, "
    "control or mitigate these risks. Statements in this section are based on the "
    "Company's beliefs and opinions regarding matters that could materially "
    "adversely affect the Company."
)

# A realistic corpus: the formula recurs in most paragraphs, as in a real filing.
CORPUS = [INTRO_OLD, SUPPLY_NEW, INTRO_NEW] + [
    f"The Company faces risks relating to {topic} that could materially adversely "
    f"affect its {FORMULA}."
    for topic in [
        "competition", "supply chain concentration", "cybersecurity incidents",
        "antitrust litigation", "foreign exchange rates", "component pricing",
        "third-party developers", "retail operations", "tax examinations",
        "climate and natural disasters", "data privacy regulation", "seasonality",
    ]
]


def main():
    idf = build_idf(CORPUS)

    false_t = token_similarity(INTRO_OLD, SUPPLY_NEW)
    true_t = token_similarity(INTRO_OLD, INTRO_NEW)
    false_i = weighted_similarity(INTRO_OLD, SUPPLY_NEW, idf)
    true_i = weighted_similarity(INTRO_OLD, INTRO_NEW, idf)

    print(f"{'pair':<30} {'jaccard':>9} {'idf-weighted':>14}")
    print("-" * 56)
    print(f"{'FALSE (intro vs supply)':<30} {false_t:>9.3f} {false_i:>14.3f}")
    print(f"{'TRUE  (intro vs intro)':<30} {true_t:>9.3f} {true_i:>14.3f}")
    print()
    print(f"jaccard orders them correctly: {true_t > false_t}")
    print(f"idf orders them correctly    : {true_i > false_i}")
    if false_i:
        print(f"idf margin                   : {true_i / false_i:.1f}x")
    print()

    print("lowest-weight terms (the formula, discovered not hand-listed):")
    for tok, w in sorted(idf.items(), key=lambda x: x[1])[:8]:
        print(f"   {tok:<14} {w:.3f}")
    print("\nhighest-weight terms:")
    for tok, w in sorted(idf.items(), key=lambda x: -x[1])[:5]:
        print(f"   {tok:<14} {w:.3f}")

    return true_i > false_i


if __name__ == "__main__":
    ok = main()
    print(f"\n{'PASS' if ok else 'FAIL'}")
