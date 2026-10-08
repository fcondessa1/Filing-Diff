"""
Tests for store.py, ask.py and eval_rag.py, with no network, model download
or API key.

A tiny stand-in embedder replaces the sentence-transformers model. It maps a
few synonyms to the same dimension ("duties" -> "tariff"), which is enough to
show the property that matters: vector search finds a passage that shares
meaning but no words with the question, keyword search does not, and hybrid
search keeps both.

Run: python test_rag.py
"""

import hashlib
import json
import re
from types import SimpleNamespace

import numpy as np

import ask
import eval_rag
import store
from store import collapse_versions

SYNONYMS = {"duties": "tariff", "duty": "tariff", "tariffs": "tariff", "levies": "tariff",
            "children": "minor", "kids": "minor", "minors": "minor"}
DIM = 4096  # wide enough that unrelated words almost never share a bucket
STOP = frozenset("the a an and or of to in on for with as at by is are be can could will "
                 "would its it this that from which has have was were".split())


class FakeEmbedder:
    name = "fake-hash-embedder"

    def _vec(self, text):
        v = np.zeros(DIM, dtype=np.float32)
        for w in re.findall(r"[a-z]+", text.lower()):
            if w in STOP:
                continue
            w = SYNONYMS.get(w, w)
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % DIM] += 1
        n = np.linalg.norm(v)
        return v / n if n else v

    def embed_passages(self, texts):
        return np.stack([self._vec(t) for t in texts])

    def embed_query(self, text):
        return self._vec(text)


TARIFF = ("Beginning in the second quarter of 2025, new tariffs were announced on imports "
          "to the U.S., which have increased the Company's costs and could materially "
          "adversely affect its gross margins.")
SAFETY = ("The Company is also subject to new and changing laws regarding online safety, "
          "including enhanced protections for minors and mandatory age verification "
          "requirements.")
GOOGLE = ("On August 5, 2024, Google was found to have violated U.S. antitrust laws. "
          "Remedies could materially adversely affect the Company's ability to earn revenue "
          "from licensing arrangements with Google.")
OLD_RISK = ("The Company's business can be affected by changes in trade policy between the "
            "U.S. and China, which have in the past led to restrictions affecting the "
            "Company's business and its supply chain partners in Asia.")


def build_db():
    conn = store.connect(":memory:")
    emb = FakeEmbedder()
    store.add_filing(conn, emb, "AAPL", "0000320193",
                     {"form": "10-K", "filing_date": "2024-11-01", "accession": "a1", "url": "u1"},
                     {"risk_factors": OLD_RISK + "\n\n" + GOOGLE})
    store.add_filing(conn, emb, "AAPL", "0000320193",
                     {"form": "10-K", "filing_date": "2025-10-31", "accession": "a2", "url": "u2"},
                     {"risk_factors": TARIFF + "\n\n" + SAFETY, "mdna": GOOGLE})
    store.add_filing(conn, emb, "MSFT", "0000789019",
                     {"form": "10-K", "filing_date": "2025-07-30", "accession": "m1", "url": "u3"},
                     {"risk_factors": "Tariffs on imports could raise the cost of Microsoft's "
                                      "devices, reduce demand for hardware products and "
                                      "adversely affect the gross margins of its devices business."})
    return conn, emb


def show(checks: dict, title: str) -> bool:
    print(f"\n=== {title} ===")
    for label, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {label}")
    return all(checks.values())


def test_chunking():
    long_para = " ".join(f"Sentence number {i} describes a separate risk in detail." for i in range(60))
    chunks = store.chunk_section("Short heading\n\n" + long_para + "\n\n" + TARIFF)
    return show({
        "short fragment (heading) dropped": all("Short heading" != c for c in chunks),
        "long paragraph split into several chunks": len(chunks) >= 3,
        "no chunk longer than the cap": all(len(c) <= store.MAX_CHUNK_CHARS for c in chunks),
        "split happens at sentence boundaries": all(c.rstrip().endswith(".") for c in chunks),
        "normal paragraph kept whole": TARIFF in chunks,
    }, "chunking")


def test_storage_and_sql():
    conn, _ = build_db()
    counts = conn.execute(
        "SELECT f.ticker, COUNT(c.id) n FROM filings f JOIN sections s ON s.filing_id=f.id "
        "JOIN chunks c ON c.section_id=s.id GROUP BY f.ticker ORDER BY f.ticker").fetchall()
    fts_rows = conn.execute("SELECT COUNT(*) FROM chunk_fts").fetchone()[0]
    chunk_rows = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    dup = False
    try:
        store.add_filing(conn, FakeEmbedder(), "AAPL", "x",
                         {"form": "10-K", "filing_date": "d", "accession": "a1", "url": "u"}, {})
    except Exception:
        dup = True
    return show({
        "chunks stored per ticker in SQL tables": [tuple(r) for r in counts] == [("AAPL", 5), ("MSFT", 1)],
        "every chunk is in the full-text index": fts_rows == chunk_rows,
        "same filing cannot be stored twice (accession is unique)": dup,
    }, "storage")


def test_search():
    conn, emb = build_db()
    # Shares no word (even after stemming) with the tariff passage.
    q = "Will customs duties hurt profitability?"

    def ids(mode, k=5):
        return [p["text"] for p in store.search(conn, emb, "AAPL", q, k=k, mode=mode)]

    kw, vec, hyb = ids("keyword"), ids("vector"), ids("hybrid")
    msft = store.search(conn, emb, "MSFT", "tariffs", k=5)
    awkward = store.search(conn, emb, "AAPL", 'what about "Section 232" (semiconductors)?!', k=3)
    return show({
        "vector search ranks the tariff passage first for 'customs duties'": vec[0] == TARIFF,
        "keyword search alone does not rank it first (no shared word 'tariffs')":
            not kw or kw[0] != TARIFF,
        "hybrid keeps the vector hit in its top 2": TARIFF in hyb[:2],
        "results are limited to the requested ticker":
            all("Microsoft" not in t for t in hyb) and "Microsoft" in msft[0]["text"],
        "punctuation and quotes in a question do not break full-text search":
            isinstance(awkward, list),
        "stemming: 'import costs' keyword-matches 'imports' / 'costs'":
            TARIFF in [p["text"] for p in store.search(conn, emb, "AAPL", "import cost", k=3,
                                                       mode="keyword")],
        "fusion rewards agreement between rankings":
            store.fuse([[1, 2, 3], [3, 2, 1], [2, 9]])[0] == 2,
    }, "search")


class FakeClient:
    def __init__(self, answer):
        self.answer, self.sent, self.messages = answer, {}, self

    def create(self, **kwargs):
        self.sent = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps(self.answer))],
            usage=SimpleNamespace(input_tokens=2000, output_tokens=300))


def test_ask_verification():
    conn, emb = build_db()
    passages = store.search(conn, emb, "AAPL", "tariffs and google antitrust", k=10)
    tariff_id = next(p["id"] for p in passages if p["text"] == TARIFF)
    google_ids = [p["id"] for p in passages if p["text"] == GOOGLE]
    other_id = next(p["id"] for p in passages if p["text"] not in (GOOGLE,) and p["id"] != tariff_id)

    answer = {
        "coverage": "answered",
        "answer": "Apple added tariff costs in 2025 and flags the Google remedies.",
        "claims": [
            {"statement": "New tariffs were announced in 2025.",
             "citations": [{"passage_id": tariff_id,
                            "quote": "new tariffs were announced on imports to the U.S."}]},
            {"statement": "Google was found to have violated antitrust law.",
             "citations": [{"passage_id": other_id,
                            "quote": "Google was found to have violated U.S. antitrust laws"}]},
            {"statement": "Tariffs will cut margins by 2 points.",
             "citations": [{"passage_id": tariff_id, "quote": "tariffs will cut margins by two points"}]},
            {"statement": "Something from nowhere.",
             "citations": [{"passage_id": 99999, "quote": "new tariffs were announced"}]},
        ],
    }
    client = FakeClient(answer)
    result = ask.ask(client, conn, emb, "AAPL", "tariffs and google antitrust", k=10,
                     model="claude-haiku-4-5-20251001")
    statuses = [c["status"] for c in result["check"]["claims"]]
    problems = [c["citations"][0]["problem"] for c in result["check"]["claims"]]
    prompt = client.sent["messages"][0]["content"]
    first_2024 = prompt.find("filed 2024")
    first_2025 = prompt.find("filed 2025")
    md = ask.render(result)

    return show({
        "structured output requested": "output_config" in client.sent,
        "passages shown oldest first": 0 <= first_2024 < first_2025,
        "faithful quote in the cited passage -> VERIFIED": statuses[0] == "VERIFIED",
        "real quote cited to the wrong passage -> UNSUPPORTED, says where it is":
            statuses[1] == "UNSUPPORTED" and problems[1].startswith("quote is in passage")
            and int(problems[1].split()[4].rstrip(",")) in google_ids,
        "invented quote -> UNSUPPORTED": statuses[2] == "UNSUPPORTED" and problems[2] == "quote not found in passage",
        "citation to a passage that was never provided -> UNSUPPORTED":
            problems[3] == "cites a passage that was not provided",
        "rendered answer flags unverified claims": "**[UNSUPPORTED]**" in md and "✓" in md,
    }, "ask: citation checks")


def test_not_in_sources():
    conn, emb = build_db()
    client = FakeClient({"coverage": "not_in_sources",
                         "answer": "The passages do not discuss dividends.", "claims": []})
    result = ask.ask(client, conn, emb, "AAPL", "What is the dividend policy?", k=5,
                     model="claude-haiku-4-5-20251001")
    empty = ask.ask(client, conn, emb, "ZZZZ", "anything", k=5)
    return show({
        "model can decline to answer": result["coverage"] == "not_in_sources",
        "no claims means nothing marked verified": result["check"]["counts"]["VERIFIED"] == 0,
        "unknown ticker returns a clear error, no API call":
            empty.get("error") == "no passages found",
    }, "ask: declining")


def test_eval():
    conn, emb = build_db()
    questions = [("Will customs duties hurt profitability?", ["new tariffs"]),
                 ("What obligations exist for kids' internet use?", ["age verification"]),
                 ("Did a court rule against Google?", ["violated u.s. antitrust laws"])]
    res = eval_rag.evaluate(conn, emb, "AAPL", questions)
    return show({
        "all three modes scored": set(res) == set(eval_rag.MODES),
        "hybrid finds every answer in the top 5": res["hybrid"]["hit@5"] == 1.0,
        "vector beats keyword on reworded questions (MRR)":
            res["vector"]["mrr"] > res["keyword"]["mrr"],
        "rank of first hit computed": eval_rag.first_hit_rank(
            [{"text": "x"}, {"text": SAFETY}], ["age verification"]) == 2,
    }, "retrieval eval")


def test_ingest_skips_indexed(monkeypatch_targets=None):
    import edgar
    import sections

    filings = [{"form": "10-K", "filing_date": "2025-10-31", "accession": "k1", "url": "u-k1"},
               {"form": "10-Q", "filing_date": "2026-01-30", "accession": "q1", "url": "u-q1"}]
    fetched = []
    saved = (edgar.get_cik, edgar.list_filings, edgar.fetch_document, sections.extract_sections)
    edgar.get_cik = lambda t: "0000320193"
    edgar.list_filings = lambda cik, form_types, limit: filings[:limit]
    edgar.fetch_document = lambda url: fetched.append(url) or url
    sections.extract_sections = lambda html, items: (
        {"1A": TARIFF, "7": GOOGLE} if html == "u-k1" else {"1A": SAFETY})
    try:
        conn = store.connect(":memory:")
        store.ingest("aapl", 2, conn, FakeEmbedder())
        first = len(fetched)
        store.ingest("AAPL", 2, conn, FakeEmbedder())
        second = len(fetched) - first
        secs = {r[0] for r in conn.execute("SELECT section FROM sections")}
    finally:
        edgar.get_cik, edgar.list_filings, edgar.fetch_document, sections.extract_sections = saved

    return show({
        "first ingest fetches both filings": first == 2,
        "second ingest fetches nothing (already indexed)": second == 0,
        "10-K Item 7 and 10-Q Item 1A mapped to named sections": secs == {"risk_factors", "mdna"},
    }, "ingest")


def test_collapse_versions():
    """
    Modelled on the first real tariff answer: one MD&A paragraph carried
    through six filings, growing as events were added, filled half of the
    twelve slots and pushed out a November 2024 passage.
    """
    base = ("Beginning in the second quarter of 2025, new tariffs were announced on imports "
            "to the U.S., including additional tariffs on imports from China, India, Japan, "
            "South Korea, Taiwan, Vietnam and the EU. Several countries have imposed reciprocal "
            "tariffs on imports from the U.S. and other retaliatory measures.")
    s232 = (" On January 14, 2026, initial results were published of the Section 232 "
            "investigation into imports of semiconductors, which did not impose additional "
            "tariffs on the Company's products.")
    scotus = (" On February 20, 2026, the Supreme Court issued a ruling striking down certain "
              "tariffs, and the Company applied for refunds of tariffs paid.")
    versions = [  # (id, form, date, text) -- the Section 232 sentence is later dropped
        (389, "10-Q", "2025-05-02", base),
        (332, "10-Q", "2025-08-01", base),
        (291, "10-K", "2025-10-31", base),
        (149, "10-Q", "2026-01-30", base + s232),
        (106, "10-Q", "2026-05-01", base + scotus),
        (33, "10-Q", "2026-07-31", base + scotus),
    ]
    other = [
        (34, "10-Q", "2026-07-31",
         "Various modifications to U.S. tariffs have been announced, including the recent "
         "imposition of tariffs under Section 301 of the Trade Act of 1974. The ultimate impact "
         "remains uncertain and will depend on several factors."),
        (372, "10-Q", "2025-05-02",
         "Changing the Company's business and supply chain in accordance with new or changed "
         "restrictions on international trade can be expensive, time-consuming and disruptive."),
        (510, "10-K", "2024-11-01",
         "Tensions between governments, including the U.S. and China, have in the past led to "
         "tariffs and other restrictions affecting the Company's business, and could do so again."),
    ]

    def mk(i, form, date, text):
        return {"id": i, "form": form, "filing_date": date, "text": text,
                "section": "mdna", "url": "u"}

    # Relevance order as retrieved: all six versions outrank the 2024 passage.
    ranked = [mk(*v) for v in versions] + [mk(*o) for o in other]
    k = 5
    without = ranked[:k]
    kept = collapse_versions(ranked, k)
    ids = [p["id"] for p in kept]
    by_id = {p["id"]: p for p in kept}
    span = by_id.get(33, {}).get("span") or {}

    prompt = ask.format_passages(kept)

    return show({
        "before: top 5 are all versions of one paragraph, no 2024 passage":
            all(p["id"] in {v[0] for v in versions} for p in without),
        "after: earliest (389) and latest (33) versions kept": 389 in ids and 33 in ids,
        "after: unchanged middle copies dropped (332, 291, 106)": not {332, 291, 106} & set(ids),
        "after: version with a sentence later dropped (149, Section 232) kept": 149 in ids,
        "after: freed slots reach other paragraphs, incl. Section 301 (34)": 34 in ids,
        "span records 6 versions, 2025-05-02 to 2026-07-31":
            span.get("versions") == 6 and span.get("first", (0, 0))[1] == "2025-05-02"
            and span.get("last", (0, 0))[1] == "2026-07-31",
        "paragraphs sharing only boilerplate are not merged":
            by_id.get(34, {}).get("span") is None,
        "never more than k passages": len(kept) <= k,
        "model is told the span": "appears in 6 filings" in prompt,
        "with room, the 2024 passage gets in": 510 in [p["id"] for p in collapse_versions(ranked, 7)],
    }, "collapsing repeated paragraphs")


def test_relevance_bar_and_query():
    """
    From the second live run: collapsing freed slots that went to regional
    net-sales paragraphs, while a November 2024 passage containing "tariffs"
    ranked 47th because "last two years" swamped the keyword search.
    """
    def mk(i, date, text):
        return {"id": i, "form": "10-Q", "filing_date": date, "text": text,
                "section": "mdna", "url": "u"}

    tariff = ("Beginning in the second quarter of 2025, new tariffs were announced on imports "
              "to the U.S., including additional tariffs on imports from China and other "
              "countries, which can affect the Company's gross margin.")
    ranked = (
        [mk(100 + n, d, tariff) for n, d in enumerate(
            ["2025-05-02", "2025-08-01", "2025-10-31", "2026-01-30"])]        # 4 copies in top 5
        + [mk(200, "2026-07-31", "Various modifications to U.S. tariffs have been announced, "
                                 "including tariffs under Section 301 of the Trade Act of 1974.")]
        + [mk(300, "2026-05-01", "Greater China net sales increased during the second quarter "
                                 "compared to the same period in 2025 due to higher net sales of iPhone.")]
        + [mk(400, "2024-11-01", "Tensions between governments, including the U.S. and China, have "
                                 "in the past led to tariffs and other restrictions affecting the "
                                 "Company's business.")]
    )
    on_topic = {p["id"] for p in ranked if "tariff" in p["text"]}
    gated = [p["id"] for p in collapse_versions(ranked, 5, eligible_extra=on_topic)]
    ungated = [p["id"] for p in collapse_versions(ranked, 5)]

    return show({
        "time words dropped: '...tariffs over the last two years?' -> tariffs only":
            store.fts_query("What has Apple said about tariffs over the last two years?") == '"tariffs"',
        "capitalised acronyms kept: 'AI', 'EU'":
            '"ai"' in store.fts_query("How has Apple described AI risks?")
            and '"eu"' in store.fts_query("Which EU law applies?"),
        "lower-case two-letter filler still dropped": store.fts_query("what is it on") is None,
        "each method keeps more than 50 results": store.RANK_DEPTH > 50,
        "without the bar, the off-topic sales paragraph takes a freed slot": 300 in ungated,
        "with the bar, it does not": 300 not in gated,
        "with the bar, the on-topic 2024 passage gets the slot": 400 in gated,
        "original top-k passages are never filtered out": 200 in gated,
    }, "relevance bar and keyword query")


def test_truncated_reply_refused():
    """From a live run: the answer outgrew max_tokens and the JSON was cut off."""
    from summarise import TruncatedResponse

    class CutOff(FakeClient):
        def create(self, **kwargs):
            self.sent = kwargs
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text='{"coverage": "answered", "answer": "Apple first')],
                usage=SimpleNamespace(input_tokens=5000, output_tokens=1500),
                stop_reason="max_tokens")

    conn, emb = build_db()
    client = CutOff({})
    try:
        ask.ask(client, conn, emb, "AAPL", "tariffs", k=5, model="claude-sonnet-5-5")
        raised, message = False, ""
    except TruncatedResponse as e:
        raised, message = True, str(e)
    return show({
        "cut-off reply raises TruncatedResponse, not a JSON parse error": raised,
        "error says what happened and what to do": "max_tokens" in message and "Raise" in message,
        "answers have room: cap well above the 1,465 tokens a real answer used":
            client.sent.get("max_tokens", 0) >= 4000,
    }, "truncated replies")


def test_numbers_distinguish_versions():
    """
    From the third live run: the May 2026 version of a tariff paragraph named
    Section 122, the July 2026 version Section 301. Comparing letters only,
    they were identical, the May version was dropped, and the answer lost
    Section 122.
    """
    def mk(i, date, text):
        return {"id": i, "form": "10-Q", "filing_date": date, "text": text,
                "section": "mdna", "url": "u"}

    tail = (" and further changes could be made. The ultimate impact remains uncertain and will "
            "depend on several factors, including the overall magnitude and duration of these measures.")
    mods = [
        mk(1, "2025-05-02", "Various modifications to U.S. tariffs have been announced," + tail),
        mk(2, "2026-05-01", "Various modifications to U.S. tariffs have been announced, including the "
                            "imposition of tariffs under Section 122 of the Trade Act of 1974," + tail),
        mk(3, "2026-07-31", "Various modifications to U.S. tariffs have been announced, including the "
                            "recent imposition of tariffs under Section 301 of the Trade Act of 1974," + tail),
    ]
    margin = ("Products gross margin increased during the {q} quarter of {y} compared to the {q} "
              "quarter of {p} due primarily to a different mix of products, partially offset by tariffs.")
    quarterly = [
        mk(11, "2025-08-01", margin.format(q="third", y=2025, p=2024)),
        mk(12, "2026-01-30", margin.format(q="first", y=2026, p=2025)),
        mk(13, "2026-05-01", margin.format(q="second", y=2026, p=2025)),
    ]
    kept_mods = {p["id"] for p in collapse_versions(mods, 10)}
    kept_q = {p["id"] for p in collapse_versions(quarterly, 10)}
    words = store._content_words("Section 122 of the Trade Act of 1974")

    return show({
        "numbers count as content words": "122" in words,
        "the Section 122 version (May 2026) is kept": 2 in kept_mods,
        "the Section 301 version (latest) is kept": 3 in kept_mods,
        "quarter-to-quarter edits with rolled-forward years still collapse to one copy":
            kept_q == {13},
        "years alone are not 'new numbers'":
            not store._new_numbers({"2026", "gross"}, {"2025", "gross"}),
    }, "numbers distinguish versions")


if __name__ == "__main__":
    results = [test_chunking(), test_storage_and_sql(), test_search(),
               test_ask_verification(), test_not_in_sources(), test_eval(),
               test_ingest_skips_indexed(), test_collapse_versions(),
               test_relevance_bar_and_query(), test_truncated_reply_refused(),
               test_numbers_distinguish_versions()]
    print(f"\n{sum(results)}/{len(results)} checks passed")
