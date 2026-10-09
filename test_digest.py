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
NO_CHANGES = ("Item 1A. Risk Factors\n\nThere have been no material changes to the risk factors "
              "disclosed in our Annual Report on Form 10-K for the year ended December 31, 2025.")
RISK_NEW = RISK_OLD + (
    "\n\nThe Company is also subject to new laws on online safety, including protections for "
    "minors and mandatory age verification requirements, which may require costly changes.")


def filing(acc, form, date):
    return {"accession": acc, "form": form, "filing_date": date, "url": f"https://sec.gov/{acc}"}


class FakeClient:
    """Answers every call with a valid structured response; counts calls."""
    def __init__(self):
        self.calls = 0
        self.sent = []
        self.messages = self

    def create(self, **kwargs):
        self.calls += 1
        self.sent.append(kwargs["messages"][0]["content"])
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
        "compared with the previous 10-Q, not the 10-K": "compared with [10-Q of 30 Jan 2026](https://sec.gov/q1)" in text,
        "the added risk is summarised": "age verification" in text and client.calls >= 1,
        "high-materiality change listed under High importance": "## 🔴 High importance (1)" in text,
        "the model is told whose filing it is": client.sent and "COMPANY: AAPL" in client.sent[0],
        "filing recorded as processed": "q2" in state["AAPL"],
        "previous-of-same-form skips the 10-K": digest.previous_of_same_form([q2, q1, k25], q2) == q1
            and digest.previous_of_same_form([k25, q2, q1], k25) is None,
    }, "new 10-Q")


def test_missing_section_and_errors(tmp):
    fresh_dirs(tmp, "errors")
    w = World()
    q1, q2 = filing("q1", "10-Q", "2026-01-30"), filing("q2", "10-Q", "2026-05-01")
    w.filings["AAPL"] = [q2, q1]
    w.texts = {q1["url"]: RISK_OLD, q2["url"]: NO_CHANGES}   # 10-Q says "no material changes"
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
        "a 'no material changes' 10-Q is quoted, not diffed, and costs no API call":
            "No changes reported" in text and "no material changes to the risk factors" in text
            and client.calls == 0,
        "one ticker failing does not stop the others": "AAPL 10-Q" in title and "MSFT error" in title,
        "the error is in the digest": "**Errors**" in text and "EDGAR unreachable" in text,
        "errors count as news (so you hear about them)": news and news2,
        "a filing that failed to process is not recorded, so it is retried":
            "q2" not in state2["AAPL"],
        "a filing that processed (even with nothing to report) is recorded": "q2" in state["AAPL"],
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
    first_text = (digest.DIGEST_DIR / "2026-05-04.md").read_text()
    path_next, news_next, _ = digest.run(FakeClient(), "claude-haiku-4-5-20251001", ["AAPL"],
                                         today="2026-05-04")

    return show({
        "first run with force_latest summarises the latest filing": news and "AAPL 10-Q" in title,
        "and still records all listed filings": set(state["AAPL"]) == {"q1", "q2"},
        "so the next normal run has nothing new": not news_next,
        "a second run on the same day does not overwrite the first":
            path_next.name == "2026-05-04-2.md"
            and (digest.DIGEST_DIR / "2026-05-04.md").read_text() == first_text,
    }, "force latest")


def test_10k_extraction_failure(tmp):
    fresh_dirs(tmp, "k_fail")
    w = World()
    k24, k25 = filing("k24", "10-K", "2024-11-01"), filing("k25", "10-K", "2025-10-31")
    w.filings["NVDA"] = [k25, k24]
    w.texts = {k24["url"]: RISK_OLD, k25["url"]: None}
    w.install()
    digest.save_state({"NVDA": ["k24"]})
    path, news, title = digest.run(FakeClient(), "claude-haiku-4-5-20251001", ["NVDA"], today="2025-11-03")
    text = path.read_text()
    return show({
        "missing Risk Factors in a 10-K is reported as a parsing failure":
            "Could not find the Risk Factors heading" in text and "parsing failure" in text,
        "not explained away as 'no material changes'": "no material changes" not in text,
        "the issue title flags it": "(extraction failed)" in title,
    }, "10-K extraction failure")


def test_updates_after_no_changes(tmp):
    fresh_dirs(tmp, "updates")
    w = World()
    q1, q2 = filing("q1", "10-Q", "2026-05-07"), filing("q2", "10-Q", "2026-08-10")
    w.filings["IONQ"] = [q2, q1]
    w.texts = {q1["url"]: NO_CHANGES, q2["url"]: RISK_NEW}
    w.install()
    digest.save_state({"IONQ": ["q1"]})
    client = FakeClient()
    path, news, title = digest.run(client, "claude-haiku-4-5-20251001", ["IONQ"], today="2026-08-10")
    text = path.read_text()
    rows = json.loads((digest.DIGEST_DIR / "2026-08-10.json").read_text())["IONQ"][0]["rows"]
    return show({
        "the earlier 'no changes' statement is explained": "reported no changes" in text,
        "every paragraph of the updates is reported as added":
            rows and all(r["kind"] == "added" for r in rows) and len(rows) == 3,
        "nothing is reported as removed": "REMOVED" not in text,
        "not flagged as an extraction failure": "(extraction failed)" not in title,
    }, "updates after a 'no changes' quarter")


def test_join_fragments(tmp):
    headline = ("The SkyWater business operates in the highly cyclical semiconductor industry, which is "
                "subject to significant downturns that may negatively impact our results of operations.")
    body = ("The semiconductor industry is highly cyclical and is characterized by rapid technological "
            "change, price erosion and wide fluctuations in supply and demand. Downturns may last long.")
    headline2 = "Our sales cycles are long and unpredictable, which could adversely affect our results."
    body2 = "Sales typically require lengthy cycles. Customers can be complex and require education."
    text = "\n\n".join(["Risks Related to the SkyWater Acquisition", headline, body, headline2, body2])
    joined = digest.join_fragments(text).split("\n\n")

    broken = ("Violations of export controls could result in significant penalties, and the penalties available"
              "\n\n42\n\nTable of Contents\n\n"
              "under these rules could have a material and adverse impact on our business.")
    mended = digest.join_fragments(broken).split("\n\n")

    two_headlines = "\n\n".join([headline, headline2, body2])
    kept = digest.join_fragments(two_headlines).split("\n\n")

    list_intro = "Our results could be affected by the following factors, as well as:\n\nchanges in interest rates;"

    # Cases from the first check on real filings (check_joining.py).
    intro = ("Other than the risk factors listed below, there have been no material changes from the "
             "risk factors previously described in our Annual Report on Form 10-K.")
    msft_head = ("We face intense competition across all markets for our products and services, which "
                 "could adversely affect our results of operations.")
    sub = "Competition in the technology sector"
    msft_body = ("Our competitors range in size from diversified global companies to small, specialized "
                 "firms. Barriers to entry in many of our businesses are low.")
    real = digest.join_fragments("\n\n".join([intro, msft_head, sub, msft_body])).split("\n\n")
    bullet = "\u2022\ngeopolitical events, including war and terrorism."
    after_bullet = ("As international retail and cloud services grow, competition will intensify. "
                    "Local companies may have a substantial competitive advantage.")
    amzn = ("Governments may ultimately enforce these rules in a way that courts\n\nTable of "
            "\nContents ultimately take a view contrary to ours.")
    return show({
        "the section's 'no material changes' opening is not a headline": real[0] == intro,
        "a headline is not joined to a subheading": msft_head in real and sub in real,
        "a bullet point is not a headline":
            len(digest.join_fragments(f"{bullet}\n\n{after_bullet}").split("\n\n")) == 2,
        "a 'Table of Contents' link glued to the text is removed and the sentence rejoined":
            digest.join_fragments(amzn) == ("Governments may ultimately enforce these rules in a way "
                                            "that courts ultimately take a view contrary to ours."),
        "each headline is joined to its body": joined == [
            "Risks Related to the SkyWater Acquisition", f"{headline} {body}", f"{headline2} {body2}"],
        "a sentence split by a page break is rejoined, page furniture dropped":
            mended == ["Violations of export controls could result in significant penalties, and the "
                       "penalties available under these rules could have a material and adverse impact "
                       "on our business."],
        "a headline followed by another headline is not joined to it":
            kept == [headline, f"{headline2} {body2}"],
        "a list introduced by a colon is left alone": len(digest.join_fragments(list_intro).split("\n\n")) == 2,
    }, "joining headlines and page-break fragments")


def test_updates_only(tmp):
    fresh_dirs(tmp, "updates_only")
    w = World()
    q1, q2 = filing("q1", "10-Q", "2026-05-20"), filing("q2", "10-Q", "2026-08-26")
    opening = ("Other than the risk factors listed below, there have been no material changes from "
               "the risk factors previously described in our Annual Report on Form 10-K and our "
               "Quarterly Report on Form 10-Q for the quarter ended April 26, 2026.")
    supply = ("Long manufacturing lead times and uncertain supply and capacity availability, combined "
              "with a failure to estimate customer demand accurately, could lead to mismatches "
              "between supply and demand. We have experienced lead times of more than 12 months.")
    licence = ("Beginning in August 2025, the government granted licenses that would allow us to ship "
               "certain products to certain customers. Officials expressed an expectation that the "
               "government will receive 15% or more of the revenue from licensed sales.")
    licence_new = ("Beginning in August 2025, the government granted licenses that would have allowed "
                   "us to ship certain products to certain customers, but such sales were restricted "
                   "abroad. We were unable to sell our inventory under those licenses.")
    w.filings["NVDA"] = [q2, q1]
    w.texts = {q1["url"]: "\n\n".join([opening, supply, licence]),
               q2["url"]: "\n\n".join([opening, licence_new])}
    w.install()
    digest.save_state({"NVDA": ["q1"]})
    client = FakeClient()
    path, news, title = digest.run(client, "claude-haiku-4-5-20251001", ["NVDA"], today="2026-08-31")
    text = path.read_text()
    result = json.loads((digest.DIGEST_DIR / "2026-08-31.json").read_text())["NVDA"][0]
    return show({
        "an updates-only section is recognised": digest.is_updates_only(opening),
        "a full section is not": not digest.is_updates_only(
            "Please carefully consider the following discussion of significant factors."),
        "a left-out paragraph with no successor is listed as not repeated, not removed":
            len(result["not_repeated"]) == 1 and "Long manufacturing lead times" in text
            and "not repeated" in text,
        "and costs no model call": not any("Long manufacturing" in m for m in client.sent),
        "a rewritten paragraph is still judged by the model":
            any(r["old"] == licence for r in result["rows"]),
        "the digest says the earlier 10-Q still stands": "earlier 10-Qs still stand" in text,
    }, "updates-only 10-Q")


def test_layout(tmp):
    fresh_dirs(tmp, "layout")
    w = World()
    q1, q2 = filing("q1", "10-Q", "2026-05-07"), filing("q2", "10-Q", "2026-08-10")
    w.filings["IONQ"] = [q2, q1]
    w.texts = {q1["url"]: RISK_OLD, q2["url"]: RISK_NEW}
    w.install()
    digest.save_state({"IONQ": ["q1"]})

    class StoryClient(FakeClient):
        def create(self, **kwargs):
            if "headline" in json.dumps(kwargs.get("output_config", {})):
                self.calls += 1
                story = {"headline": "New online-safety rules"}
                return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(story))],
                                       usage=SimpleNamespace(input_tokens=300, output_tokens=40),
                                       stop_reason="end_turn")
            return super().create(**kwargs)

    path, _, _ = digest.run(StoryClient(), "claude-haiku-4-5-20251001", ["IONQ"], today="2026-08-12")
    text = path.read_text()
    broken, _, _ = (None, None, None)
    fresh_dirs(tmp, "layout_nostory")
    w.install()
    digest.save_state({"IONQ": ["q1"]})
    path2, _, _ = digest.run(FakeClient(), "claude-haiku-4-5-20251001", ["IONQ"], today="2026-08-12")
    text2 = path2.read_text()
    return show({
        "an at-a-glance table opens the digest": "| Company | Filing | What changed | 🔴 High | 🟡 Medium | ⚪ Low |" in text,
        "the headline appears in the table": "| New online-safety rules |" in text,
        "no story paragraphs (they were not checkable)": "\n> " not in text,
        "both filings are linked": "[10-Q of 10 Aug 2026](https://sec.gov/q2)" in text
            and "[10-Q of 7 May 2026](https://sec.gov/q1)" in text,
        "a headline adding a number not in the summaries is dropped":
            digest.headline_problem("A $40 billion buyback", "GOOGL", "share sale programme") is not None,
        "a headline naming the ticker is dropped":
            digest.headline_problem("NVDA's AI bets create risks", "NVDA", "AI bets") is not None,
        "a clean headline passes":
            digest.headline_problem("SkyWater acquisition brings foundry risks", "IONQ",
                                    "SkyWater acquisition foundry") is None,
        "summaries lose the 'The company added a new risk factor regarding' opening":
            digest.short_summary("The company added a new risk factor regarding long and "
                                 "unpredictable sales cycles for the SkyWater business.")
            == "Long and unpredictable sales cycles for the SkyWater business."
            and digest.short_summary("The company added disclosure that legal demands for "
                                     "customer data are increasing.")
            == "Legal demands for customer data are increasing.",
        "dates are readable": "10 Aug 2026" in text,
        "technical detail is folded away": "<details><summary>Run details</summary>" in text,
        "without a story the digest still works": "| **IONQ** |" in text2 and "High importance" in text2,
    }, "readable layout")


if __name__ == "__main__":
    tmp = Path(tempfile.mkdtemp())
    saved = (edgar.get_cik, edgar.list_filings, digest.risk_factors,
             digest.DIGEST_DIR, digest.STATE_PATH, summarise.CACHE_DIR)
    cwd = os.getcwd()
    try:
        results = [test_watchlist(tmp), test_first_run_and_quiet_week(tmp), test_new_10q(tmp),
                   test_missing_section_and_errors(tmp), test_force_latest(tmp),
                   test_10k_extraction_failure(tmp), test_updates_after_no_changes(tmp),
                   test_join_fragments(tmp), test_updates_only(tmp),
                   test_layout(tmp)]
    finally:
        (edgar.get_cik, edgar.list_filings, digest.risk_factors,
         digest.DIGEST_DIR, digest.STATE_PATH, summarise.CACHE_DIR) = saved
        os.chdir(cwd)
        shutil.rmtree(tmp)
    print(f"\n{sum(results)}/{len(results)} checks passed")
