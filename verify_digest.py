"""
Hand-check the removals in a weekly digest, then score the model against you.

The digest reports a risk as REMOVED when a paragraph of the previous filing
has no counterpart in the new one, and the model then judges each one against
the new filing's closest paragraphs. On Apple's 10-K, hand verification found
that most such "removals" were text merged into other paragraphs. This does
the same check for any ticker in a digest.

Step 1, write the review file (fetches the filings, no API calls):

    python verify_digest.py NVDA > results/nvda_verification.txt

For each removal it shows the removed paragraph, the three paragraphs of the
new filing that contain most of it (what the model saw), and the closest
paragraph in the company's latest 10-K. The model's verdict is not shown, so
your judgment is independent. Write a verdict on each "your verdict:" line.

Step 2, score:

    python verify_digest.py NVDA --score results/nvda_verification.txt

Why the 10-K is shown. Many 10-Qs list only updates ("Other than the risk
factors listed below, there have been no material changes from the risk
factors previously described in our Annual Report on Form 10-K"). Comparing
two such 10-Qs, a risk that was updated last quarter and not this quarter
looks removed, although the company still discloses it: it is simply not
repeated. The opening paragraph of each section is printed at the top so you
can see which kind of section each filing has.
"""

import argparse
import json
import re
from pathlib import Path

import digest
from summarise import load_hand_labels, normalise, removal_key, score_removals

VERDICT_GUIDE = """\
Verdicts (write one per entry; a short reason after it is useful):
  REAL          the risk is no longer disclosed: not in the new filing, and not
                still standing in the 10-K the new filing points back to
  PARTIAL       part of it survives, but a meaningful part was dropped
  MERGED        still in the new filing, combined into another paragraph
  REWORDED      still in the new filing, rewritten
  MOVED         still in the new filing, elsewhere
  NOT REPEATED  not in the new filing, but the section only lists updates and
                the risk still stands in the 10-K (the company did not drop it)
"""


def latest_digest(ticker: str) -> tuple[Path, dict]:
    """The newest digest JSON with results for this ticker."""
    def order(p: Path):
        m = re.match(r"(\d{4}-\d{2}-\d{2})(?:-(\d+))?$", p.stem)
        return (m.group(1), int(m.group(2) or 1)) if m else ("", 0)

    for path in sorted(digest.DIGEST_DIR.glob("*.json"), key=order, reverse=True):
        if path.name == digest.STATE_PATH.name:
            continue
        data = json.loads(path.read_text())
        if data.get(ticker):
            return path, data[ticker][-1]
    raise SystemExit(f"No digest in {digest.DIGEST_DIR} has results for {ticker}.")


def latest_10k(ticker: str, before: str) -> dict | None:
    from edgar import get_cik, list_filings

    tenks = list_filings(get_cik(ticker), form_types=("10-K",), limit=4)
    return next((f for f in tenks if f["filing_date"] <= before), None)


def paragraphs(text: str) -> list[str]:
    from diff2 import split_paragraphs

    return split_paragraphs(digest.join_fragments(text))


def one_line(text: str) -> str:
    return normalise(text)


def opening(text: str | None) -> str:
    if not text:
        return "(no Risk Factors section found)"
    paras = [p for p in digest.join_fragments(text).split("\n\n") if len(p) > 60]
    return one_line(paras[0]) if paras else one_line(text[:600])


def write_review(ticker: str) -> None:
    from idf import build_idf
    from verify import containment

    path, result = latest_digest(ticker)
    removals = [r for r in result["rows"] if r["kind"] == "removed"]
    new, prev = result["filing"], result["previous"]
    tenk = latest_10k(ticker, new["filing_date"])

    new_text = digest.risk_factors(new["url"])
    prev_text = digest.risk_factors(prev["url"])
    tenk_text = digest.risk_factors(tenk["url"]) if tenk else None
    tenk_paras = paragraphs(tenk_text) if tenk_text else []
    idf = build_idf([r["old"] for r in removals] + tenk_paras
                    + [c["text"] for r in removals for c in r.get("candidates") or []])

    print(f"{ticker}: hand verification of the removals in {path.name}")
    print(f"\nNEW:      {new['form']} filed {new['filing_date']}  {new['url']}")
    print(f"PREVIOUS: {prev['form']} filed {prev['filing_date']}  {prev['url']}")
    if tenk:
        print(f"10-K:     filed {tenk['filing_date']}  {tenk['url']}")
    print(f"\nHow the NEW section opens:\n  {opening(new_text)}")
    print(f"\nHow the PREVIOUS section opens:\n  {opening(prev_text)}")
    print(f"\n{len(removals)} removals to check "
          f"({len(result.get('skipped') or [])} merge artifacts were skipped by the digest).\n")
    print(VERDICT_GUIDE)

    for i, r in enumerate(removals, 1):
        print(f"--- {i}. ---")
        print(f"REMOVED ({len(r['old'])} chars):\n  {one_line(r['old'])}\n")
        print(f"CLOSEST IN THE NEW {new['form']} (what the model saw):")
        for j, c in enumerate(r.get("candidates") or [], 1):
            print(f"  [{j}] containment {c['containment']:.2f}: {one_line(c['text'])}")
        if not r.get("candidates"):
            print("  (no candidates)")
        if tenk_paras:
            score, host = max(((containment(r["old"], p, idf), p) for p in tenk_paras),
                              key=lambda x: x[0])
            print(f"\nCLOSEST IN THE 10-K filed {tenk['filing_date']} "
                  f"(containment {score:.2f}):\n  {one_line(host)}")
        print("\n  your verdict: ______________________\n")


def score(ticker: str, review: Path) -> None:
    path, result = latest_digest(ticker)
    labels = load_hand_labels(review)
    rows = [r for r in result["rows"] if r["kind"] == "removed"]
    s = score_removals(rows, labels)
    if not s:
        raise SystemExit(f"No verdicts in {review} match the removals in {path.name}. "
                         f"Fill in the 'your verdict:' lines first.")

    short = {"removed": "removed", "moved_or_reworded": "still disclosed",
             "partially_removed": "partly removed"}
    n = s["n"]
    print(f"{ticker}: {n} of {len(rows)} removals in {path.name} have a hand verdict\n")
    print(f"{'#':>3}  {'you':<16} {'model':<16} agree")
    for i, (r, hand) in enumerate(s["pairs"], 1):
        print(f"{i:>3}  {short[hand]:<16} {short[r['verdict']]:<16} "
              f"{'yes' if hand == r['verdict'] else 'no'}")

    really = sum(hand == "removed" for _, hand in s["pairs"])
    print(f"\nActually removed, by hand: {really} of {n}.")
    print(f"Exact verdict:      model {s['model_agree']}/{n}, "
          f"diff alone {s['diff_agree']}/{n}")
    print(f"Removed or not:     model {s['model_agree_binary']}/{n}, "
          f"diff alone {s['diff_agree_binary']}/{n}")
    print("\n(The diff alone calls every one of them removed.)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ticker")
    ap.add_argument("--score", type=Path, help="a review file with your verdicts filled in")
    args = ap.parse_args()
    ticker = args.ticker.upper()
    if args.score:
        score(ticker, args.score)
    else:
        write_review(ticker)


if __name__ == "__main__":
    main()
