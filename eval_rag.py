"""
Measure retrieval before trusting answers built on it.

If the passage that answers a question is not retrieved, the model cannot
answer correctly however good it is, and with the "not in sources" option it
should say so. So retrieval is scored on its own, for each search mode:

    hit@5   share of questions with an answering passage in the top 5
    hit@10  same, top 10
    MRR     mean of 1 / rank of the first answering passage (0 if none in top 20)

A passage "answers" a question if it contains one of the question's expected
phrases. The phrases were taken from Apple's FY2025 10-K, so a hit is an exact,
checkable event rather than a judgment call.

The questions are deliberately worded differently from the filing ("import
duties", not "tariffs"), which is where embeddings should beat keyword search.
Eight questions written by the person who built the system is a smoke test,
not a benchmark: it shows whether hybrid search beats either half on this
data, and catches regressions when retrieval changes.

Usage:
    python eval_rag.py AAPL
"""

import sys

from summarise import normalise

QUESTIONS = [
    ("Is Apple barred by a court from charging fees on some App Store purchases?",
     ["court order preventing it from imposing any commission"]),
    ("How could the Google search antitrust ruling hurt Apple's revenue?",
     ["google was found to have violated u.s. antitrust laws"]),
    ("What new rules about protecting children online does Apple face?",
     ["age verification"]),
    ("Which European law made Apple change how apps are distributed?",
     ["digital markets act"]),
    ("How dependent is Apple on one product?",
     ["single product"]),
    ("How do import duties affect Apple's profit margins?",
     ["tariffs and other trade restrictions", "new tariffs"]),
    ("Could AI expose Apple to intellectual property claims?",
     ["machine learning and artificial intelligence"]),
    ("Does Apple depend on a few suppliers for key components?",
     ["single or limited sources", "single-source"]),
]

MODES = ("keyword", "vector", "hybrid")
DEPTH = 20


def first_hit_rank(passages: list[dict], phrases: list[str]) -> int | None:
    wanted = [p.lower() for p in phrases]
    for rank, p in enumerate(passages, 1):
        text = normalise(p["text"]).lower()
        if any(w in text for w in wanted):
            return rank
    return None


def evaluate(conn, embedder, ticker: str, questions=QUESTIONS) -> dict:
    from store import search

    results = {}
    for mode in MODES:
        ranks = [first_hit_rank(search(conn, embedder, ticker, q, k=DEPTH, mode=mode), phrases)
                 for q, phrases in questions]
        n = len(ranks)
        results[mode] = {
            "ranks": ranks,
            "hit@5": sum(r is not None and r <= 5 for r in ranks) / n,
            "hit@10": sum(r is not None and r <= 10 for r in ranks) / n,
            "mrr": sum(1 / r for r in ranks if r) / n,
        }
    return results


def report(results: dict, questions=QUESTIONS) -> None:
    print(f"{'mode':<9}{'hit@5':>7}{'hit@10':>8}{'MRR':>7}")
    print("-" * 31)
    for mode, r in results.items():
        print(f"{mode:<9}{r['hit@5']:>7.0%}{r['hit@10']:>8.0%}{r['mrr']:>7.2f}")

    print("\nrank of first answering passage (- = not in top 20):")
    print(f"{'':<52}" + "".join(f"{m:>9}" for m in results))
    for i, (q, _) in enumerate(questions):
        cells = "".join(f"{str(r['ranks'][i] or '-'):>9}" for r in results.values())
        print(f"{q[:50]:<52}{cells}")


def main():
    from store import Embedder, connect

    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    conn = connect()
    if not conn.execute("SELECT 1 FROM filings WHERE ticker = ?", (ticker.upper(),)).fetchone():
        sys.exit(f"{ticker} is not indexed. Run: python store.py ingest {ticker}")
    report(evaluate(conn, Embedder(), ticker))


if __name__ == "__main__":
    main()
