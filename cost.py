"""
Cost model for the (not yet built) LLM summarisation layer.

The diff runs first, so the model never sees a whole filing -- only the changed
paragraphs. Cost is therefore driven by delta size, not filing size.

Prices are USD per million tokens as listed in September 2026. They move every
few months; update MODELS and re-run rather than trusting the printed numbers.

Run: python cost.py
"""

CHARS_PER_TOKEN = 4          # conservative for dense legal prose
CHARS_PER_PARAGRAPH = 750    # observed average in AAPL Item 1A

# Real AAPL FY2024 -> FY2025 result at the tuned thresholds
ADDED, REMOVED, MODIFIED = 4, 13, 46

PROMPT_OVERHEAD = 400            # instruction tokens, per call
OUTPUT_TOKENS_PER_CALL = 120     # a sentence or two plus a citation

# Whole-section sizes, for the no-diff comparison
OLD_SECTION_CHARS, NEW_SECTION_CHARS = 68_888, 68_165

MODELS = [
    ("GPT-5.6 Luna", 0.20, 1.20),
    ("Claude Sonnet 5", 2.00, 10.00),
    ("GPT-5.6 Terra", 2.00, 12.00),
    ("GPT-5.6 Sol", 4.00, 20.00),
]

WATCHLIST = 20
FILINGS_PER_YEAR = 1   # 10-Ks are annual; set to 4 to include 10-Qs


def main():
    # Modified changes send both versions so the model can describe the change.
    paragraphs_sent = ADDED + REMOVED + MODIFIED * 2
    calls = ADDED + REMOVED + MODIFIED

    input_tokens = (
        paragraphs_sent * CHARS_PER_PARAGRAPH / CHARS_PER_TOKEN
        + PROMPT_OVERHEAD * calls
    )
    output_tokens = OUTPUT_TOKENS_PER_CALL * calls

    print(f"paragraphs sent : {paragraphs_sent}")
    print(f"LLM calls       : {calls}")
    print(f"input tokens    : {input_tokens:,.0f}")
    print(f"output tokens   : {output_tokens:,.0f}\n")

    per_year = WATCHLIST * FILINGS_PER_YEAR
    print(f"{'model':<17} {'per filing':>11} {'x20':>9} {'per year':>10}")
    print("-" * 50)
    for name, price_in, price_out in MODELS:
        one = input_tokens / 1e6 * price_in + output_tokens / 1e6 * price_out
        print(f"{name:<17} ${one:>10.4f} ${one * WATCHLIST:>8.2f} ${one * per_year:>9.2f}")

    # Honest accounting: diffing first does not save tokens.
    naive_in = (OLD_SECTION_CHARS + NEW_SECTION_CHARS) / CHARS_PER_TOKEN
    print(f"\nNo-diff alternative (both whole sections, one call):")
    print(f"  input tokens: {naive_in:,.0f} vs {input_tokens:,.0f} diffed "
          f"({naive_in / input_tokens:.2f}x)")
    print("  Diffing does NOT reduce tokens: modified paragraphs go twice and")
    print("  each of the calls carries its own copy of the instructions.")
    print("  It buys output quality and per-claim traceability instead.")
    print("  Batching several changes per call would cut cost at the expense")
    print("  of citation precision.")


if __name__ == "__main__":
    main()
