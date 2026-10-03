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


if __name__ == "__main__":
    results = [test_chunking(), test_storage_and_sql(), test_search(),
               test_ask_verification(), test_not_in_sources(), test_eval(),
               test_ingest_skips_indexed()]
    print(f"\n{sum(results)}/{len(results)} checks passed")
