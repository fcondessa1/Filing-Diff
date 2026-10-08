"""
Tests for digest.py with EDGAR and Claude faked: no network, no API key.

Run: python test_digest.py
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import digest
import edgar
import summarise

RISK_OLD = (
    "The Company faces substantial competition in all of its markets from companies with "
    "significant technical, marketing and distribution resources, which could reduce margins.\n\n"
    "The Company relies on single-source partners in Asia for the final assembly of substantially "
    "all of its hardware products, and disruptions there can affect supply and cost.")
RISK_NEW = RISK_OLD + (
    "\n\nThe Company is also subject to new laws on online safety, including protections for "
    "minors and mandatory age verification requirements, which may require costly changes.")


def filing(acc, form, date):
    return {"accession": acc, "form": form, "filing_date": date, "url": f"https://sec.gov/{acc}"}


class FakeClient:
    """Answers every call with a valid structured response; counts calls."""
    def __init__(self):
        self.calls = 0
        self.messages = self

    def create(self, **kwargs):
        self.calls += 1
        answer = {"summary": "Added a new risk on online safety and age verification.",
                  "materiality": "high", "materiality_reason": "A new category of regulation.",
                  "evidence": [{"source": "new", "quote": "mandatory age verification requirements"}],
                  "verdict": "removed"}
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(answer))],
                               usage=SimpleNamespace(input_tokens=600, output_tokens=90),
                               stop_reason="end_turn")


class World:
    """A fake EDGAR whose filings and texts each test sets up."""
    def __init__(self):
        self.filings = {}      # ticker -> newest-first list
        self.texts = {}        # url -> risk factors text or None
        self.fail = set()      # tickers whose listing raises

    def install(self):
        edgar.get_cik = lambda t: t
        def list_filings(cik, form_types, limit):
            if cik in self.fail:
                raise ConnectionError("EDGAR unreachable")
            return self.filings.get(cik, [])[:limit]
        edgar.list_filings = list_filings
        digest.risk_factors = lambda url: self.texts.get(url)


def show(checks: dict, title: str) -> bool:
    print(f"\n=== {title} ===")
    for label, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {label}")
    return all(checks.values())


def fresh_dirs(tmp: Path, name: str):
    base = tmp / name
    digest.DIGEST_DIR = base / "digests"
    digest.STATE_PATH = digest.DIGEST_DIR / "state.json"
    summarise.CACHE_DIR = base / "cache"


def test_watchlist(tmp):
    p = tmp / "watch.txt"
    p.write_text("# my companies\naapl\n\nMSFT  # cloud\nAAPL\n")
    return show({"comments, blanks, case and duplicates handled":
                 digest.load_watchlist(p) == ["AAPL", "MSFT"]}, "watchlist")


def test_first_run_and_quiet_week(tmp):
    fresh_dirs(tmp, "first")
    w = World()
    w.filings["AAPL"] = [filing("q3", "10-Q", "2026-07-31"), filing("q2", "10-Q", "2026-05-01"),
                         filing("k25", "10-K", "2025-10-31")]
    w.install()
    client = FakeClient()

    _, news1, title1 = digest.run(client, "claude-haiku-4-5-20251001", ["AAPL"], today="2026-08-03")
    state = json.loads(digest.STATE_PATH.read_text())
    text1 = (digest.DIGEST_DIR / "2026-08-03.md").read_text()
    _, news2, title2 = digest.run(client, "claude-haiku-4-5-20251001", ["AAPL"], today="2026-08-10")

    return show({
        "first run reports nothing and makes no API calls": not news1 and client.calls == 0,
        "first run records every listed filing, not just the latest":
            set(state["AAPL"]) == {"q3", "q2", "k25"},
        "first run says a baseline was set": "First run for AAPL" in text1,
        "a quiet week is not news and opens no issue": not news2 and title2.endswith("nothing new"),
        "still no API calls": client.calls == 0,
    }, "first run and quiet week")


def test_new_10q(tmp):
    fresh_dirs(tmp, "new10q")
    w = World()
    k25, q1, q2 = filing("k25", "10-K", "2025-10-31"), filing("q1", "10-Q", "2026-01-30"), filing("q2", "10-Q", "2026-05-01")
    w.filings["AAPL"] = [q2, q1, k25]          # newest first, as EDGAR lists them
    w.texts = {q1["url"]: RISK_OLD, q2["url"]: RISK_NEW, k25["url"]: "x" * 5000}
    w.install()
    digest.save_state({"AAPL": ["q1", "k25"]})
    client = FakeClient()

    path, news, title = digest.run(client, "claude-haiku-4-5-20251001", ["AAPL"], today="2026-05-04")
    text = path.read_text()
    state = json.loads(digest.STATE_PATH.read_text())

    return show({
        "new 10-Q is news; issue title names it": news and "AAPL 10-Q" in title,
        "compared with the previous 10-Q, not the 10-K": "vs 10-Q filed 2026-01-30" in text,
        "the added risk is summarised": "age verification" in text and client.calls >= 1,
        "summary shown with materiality": "HIGH" in text,
        "filing recorded as processed": "q2" in state["AAPL"],
        "previous-of-same-form skips the 10-K": digest.previous_of_same_form([q2, q1, k25], q2) == q1
            and digest.previous_of_same_form([k25, q2, q1], k25) is None,
    }, "new 10-Q")


def test_missing_section_and_errors(tmp):
    fresh_dirs(tmp, "errors")
    w = World()
    q1, q2 = filing("q1", "10-Q", "2026-01-30"), filing("q2", "10-Q", "2026-05-01")
    w.filings["AAPL"] = [q2, q1]
    w.texts = {q1["url"]: RISK_OLD, q2["url"]: None}      # 10-Q says "no material changes"
    w.filings["MSFT"] = [filing("m2", "10-Q", "2026-04-29")]
    w.fail = {"MSFT"}
    w.install()
    digest.save_state({"AAPL": ["q1"], "MSFT": ["m1"]})
    client = FakeClient()

    path, news, title = digest.run(client, "claude-haiku-4-5-20251001", ["AAPL", "MSFT"],
                                   today="2026-05-04")
    text = path.read_text()
    state = json.loads(digest.STATE_PATH.read_text())

    # A processing error (not a listing error) leaves the filing unrecorded.
    fresh_dirs(tmp, "errors2")
    w2 = World()
    w2.filings["AAPL"] = [q2, q1]
    w2.texts = {q1["url"]: RISK_OLD, q2["url"]: RISK_NEW}
    w2.install()
    digest.save_state({"AAPL": ["q1"]})

    class Broken(FakeClient):
        def create(self, **kwargs):
            raise RuntimeError("API down")

    _, news2, _ = digest.run(Broken(), "claude-haiku-4-5-20251001", ["AAPL"], today="2026-05-04")
    state2 = json.loads(digest.STATE_PATH.read_text())

    return show({
        "missing Risk Factors section explained, no API call":
            "No Risk Factors section found" in text and client.calls == 0,
        "one ticker failing does not stop the others": "AAPL 10-Q" in title and "MSFT error" in title,
        "the error is in the digest": "## Errors" in text and "EDGAR unreachable" in text,
        "errors count as news (so you hear about them)": news and news2,
        "a filing that failed to process is not recorded, so it is retried":
            "q2" not in state2["AAPL"],
        "a filing that processed (even with no section) is recorded": "q2" in state["AAPL"],
    }, "missing sections and errors")


def test_force_latest(tmp):
    fresh_dirs(tmp, "force")
    w = World()
    q1, q2 = filing("q1", "10-Q", "2026-01-30"), filing("q2", "10-Q", "2026-05-01")
    w.filings["AAPL"] = [q2, q1]
    w.texts = {q1["url"]: RISK_OLD, q2["url"]: RISK_NEW}
    w.install()
    client = FakeClient()

    _, news, title = digest.run(client, "claude-haiku-4-5-20251001", ["AAPL"],
                                force_latest=True, today="2026-05-04")
    state = json.loads(digest.STATE_PATH.read_text())
    _, news_next, _ = digest.run(FakeClient(), "claude-haiku-4-5-20251001", ["AAPL"], today="2026-05-11")

    return show({
        "first run with force_latest summarises the latest filing": news and "AAPL 10-Q" in title,
        "and still records all listed filings": set(state["AAPL"]) == {"q1", "q2"},
        "so the next normal run has nothing new": not news_next,
    }, "force latest")


if __name__ == "__main__":
    tmp = Path(tempfile.mkdtemp())
    saved = (edgar.get_cik, edgar.list_filings, digest.risk_factors,
             digest.DIGEST_DIR, digest.STATE_PATH, summarise.CACHE_DIR)
    cwd = os.getcwd()
    try:
        results = [test_watchlist(tmp), test_first_run_and_quiet_week(tmp), test_new_10q(tmp),
                   test_missing_section_and_errors(tmp), test_force_latest(tmp)]
    finally:
        (edgar.get_cik, edgar.list_filings, digest.risk_factors,
         digest.DIGEST_DIR, digest.STATE_PATH, summarise.CACHE_DIR) = saved
        os.chdir(cwd)
        shutil.rmtree(tmp)
    print(f"\n{sum(results)}/{len(results)} checks passed")
