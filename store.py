"""
SQLite store of filings, sections and searchable text chunks.

Everything the question-answering step (ask.py) needs lives in one file,
data/filings.db, in plain SQL tables:

    filings   one row per 10-K / 10-Q (ticker, form, date, EDGAR URL)
    sections  extracted Risk Factors and MD&A text per filing
    chunks    paragraph-sized pieces of each section, with an embedding
    chunk_fts SQLite full-text index over the chunk text (BM25 ranking)

Retrieval is hybrid. Embeddings find passages that mean the same thing as the
question ("import duties" finds "tariffs"); keyword search finds passages
that use the exact terms (a case name, "Section 232"). Each produces a
ranking, and the two are combined with reciprocal rank fusion:

    score(chunk) = sum over rankings of 1 / (60 + rank)

which needs no tuning of how a cosine similarity compares to a BM25 score.

The full-text index uses the Porter stemmer. SQLite's default tokenizer does
not stem, so a question about "import costs" would miss a passage about
"imports" increasing the Company's "cost".
eval_rag.py measures whether the combination actually beats either alone.

Vector search is a brute-force cosine over all of a ticker's chunks in numpy.
At this scale (thousands of chunks) that takes milliseconds; a vector index
would add a dependency without making anything faster.

Embeddings come from a local sentence-transformers model, so there is no API
key and no cost. The first run downloads the model (about 130 MB).

Usage:
    python store.py ingest AAPL                # last 8 filings (10-K and 10-Q)
    python store.py ingest AAPL --filings 12
    python store.py stats
    python store.py search AAPL "import duties"
"""

import argparse
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np

DB_PATH = Path("data/filings.db")

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
# bge models are trained to embed search queries with this instruction, and
# passages without it. Leaving it off measurably hurts retrieval.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# Which Items to index, per form. MD&A is Item 7 in a 10-K but Part I Item 2
# in a 10-Q; Risk Factors is Item 1A in both (Part II in a 10-Q).
ITEMS = {
    "10-K": {"1A": "risk_factors", "7": "mdna"},
    "10-Q": {"1A": "risk_factors", "2": "mdna"},
}

MIN_CHUNK_CHARS = 130   # same cutoff as the diff, tuned in diff2.py
MAX_CHUNK_CHARS = 1500  # longer paragraphs are split at sentence boundaries

RRF_K = 60

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS filings (
    id           INTEGER PRIMARY KEY,
    ticker       TEXT NOT NULL,
    cik          TEXT NOT NULL,
    form         TEXT NOT NULL,
    filing_date  TEXT NOT NULL,
    accession    TEXT NOT NULL UNIQUE,
    url          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sections (
    id         INTEGER PRIMARY KEY,
    filing_id  INTEGER NOT NULL REFERENCES filings(id),
    section    TEXT NOT NULL,
    text       TEXT NOT NULL,
    UNIQUE (filing_id, section)
);
CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY,
    section_id  INTEGER NOT NULL REFERENCES sections(id),
    position    INTEGER NOT NULL,
    text        TEXT NOT NULL,
    embedding   BLOB,
    model       TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(text, tokenize='porter unicode61');
CREATE INDEX IF NOT EXISTS idx_filings_ticker ON filings(ticker, filing_date);
CREATE INDEX IF NOT EXISTS idx_chunks_section ON chunks(section_id);
"""


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path = Path(path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    return conn


# --------------------------------------------------------------------------- #
# Embeddings
# --------------------------------------------------------------------------- #

class Embedder:
    """Local sentence-transformers model. Vectors are L2-normalised, so a dot
    product is a cosine similarity."""

    def __init__(self, model_name: str = EMBED_MODEL):
        from sentence_transformers import SentenceTransformer

        self.name = model_name
        self.model = SentenceTransformer(model_name)

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, normalize_embeddings=True, batch_size=32,
                                 show_progress_bar=len(texts) > 64).astype(np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self.model.encode([QUERY_PREFIX + text],
                                 normalize_embeddings=True)[0].astype(np.float32)


# --------------------------------------------------------------------------- #
# Chunking
# --------------------------------------------------------------------------- #

_SENTENCE_END = re.compile(r"(?<=[.;])\s+(?=[A-Z])")


def chunk_section(text: str) -> list[str]:
    """
    Paragraphs, using the same splitter and cutoff as the diff. Paragraphs over
    MAX_CHUNK_CHARS are split at sentence boundaries: the embedding model reads
    at most 512 tokens, and one chunk covering several risks retrieves poorly.
    """
    from diff2 import split_paragraphs

    chunks = []
    for para in split_paragraphs(text, MIN_CHUNK_CHARS):
        if len(para) <= MAX_CHUNK_CHARS:
            chunks.append(para)
            continue
        current = ""
        for sentence in _SENTENCE_END.split(para):
            if current and len(current) + len(sentence) + 1 > MAX_CHUNK_CHARS:
                chunks.append(current)
                current = sentence
            else:
                current = f"{current} {sentence}".strip()
        if current:
            chunks.append(current)
    return chunks


# --------------------------------------------------------------------------- #
# Ingest
# --------------------------------------------------------------------------- #

def add_filing(conn, embedder, ticker: str, cik: str, filing: dict,
               sections: dict[str, str]) -> int:
    """Insert one filing, its sections and embedded chunks. Returns chunk count."""
    cur = conn.execute(
        "INSERT INTO filings (ticker, cik, form, filing_date, accession, url) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (ticker, cik, filing["form"], filing["filing_date"], filing["accession"], filing["url"]),
    )
    filing_id = cur.lastrowid
    n_chunks = 0
    for section, text in sections.items():
        sec_id = conn.execute(
            "INSERT INTO sections (filing_id, section, text) VALUES (?, ?, ?)",
            (filing_id, section, text),
        ).lastrowid
        pieces = chunk_section(text)
        if not pieces:
            continue
        vectors = embedder.embed_passages(pieces)
        for pos, (piece, vec) in enumerate(zip(pieces, vectors)):
            chunk_id = conn.execute(
                "INSERT INTO chunks (section_id, position, text, embedding, model) "
                "VALUES (?, ?, ?, ?, ?)",
                (sec_id, pos, piece, vec.astype(np.float32).tobytes(), embedder.name),
            ).lastrowid
            conn.execute("INSERT INTO chunk_fts (rowid, text) VALUES (?, ?)", (chunk_id, piece))
        n_chunks += len(pieces)
    conn.commit()
    return n_chunks


def ingest(ticker: str, n_filings: int = 8, conn=None, embedder=None) -> None:
    """
    Fetch the last n 10-K/10-Q filings for a ticker and index them.
    Filings already in the database are skipped, so re-running is cheap.
    """
    from edgar import fetch_document, get_cik, list_filings
    from sections import extract_sections

    conn = conn or connect()
    ticker = ticker.upper()
    cik = get_cik(ticker)
    filings = list_filings(cik, form_types=("10-K", "10-Q"), limit=n_filings)
    have = {r["accession"] for r in conn.execute("SELECT accession FROM filings")}
    todo = [f for f in filings if f["accession"] not in have]
    print(f"{ticker}: {len(filings)} filings found, {len(filings) - len(todo)} already indexed")
    if not todo:
        return

    embedder = embedder or Embedder()
    for f in todo:
        items = ITEMS[f["form"]]
        extracted = extract_sections(fetch_document(f["url"]), items=tuple(items))
        sections = {items[k]: v for k, v in extracted.items()}
        missing = sorted(set(items.values()) - set(sections))
        n = add_filing(conn, embedder, ticker, cik, f, sections)
        note = f"  (not found: {', '.join(missing)})" if missing else ""
        print(f"  {f['filing_date']}  {f['form']:<5} {n:>4} chunks{note}")


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #

CHUNK_SQL = """
SELECT c.id, c.text, c.embedding, s.section, f.form, f.filing_date, f.url, f.ticker
FROM chunks c
JOIN sections s ON s.id = c.section_id
JOIN filings f ON f.id = s.filing_id
WHERE f.ticker = ?
"""

_FTS_STOP = frozenset("""a an and are as at be by can could did do does for from has have how
in is it its of on or that the their this to was were what when where which who why will
with would about over any company companys apple has said say""".split())


def fts_query(question: str) -> str | None:
    """Turn free text into a safe FTS5 query: content words OR-ed together.
    Raw user text would break FTS5 syntax on punctuation and quotes."""
    words = [w for w in re.findall(r"[a-z0-9]+", question.lower())
             if w not in _FTS_STOP and len(w) > 2]
    return " OR ".join(f'"{w}"' for w in dict.fromkeys(words)) or None


def keyword_ranking(conn, ticker: str, question: str, limit: int = 50) -> list[int]:
    q = fts_query(question)
    if not q:
        return []
    rows = conn.execute(
        "SELECT chunk_fts.rowid AS id FROM chunk_fts "
        "JOIN chunks c ON c.id = chunk_fts.rowid "
        "JOIN sections s ON s.id = c.section_id "
        "JOIN filings f ON f.id = s.filing_id "
        "WHERE chunk_fts MATCH ? AND f.ticker = ? "
        "ORDER BY bm25(chunk_fts) LIMIT ?",
        (q, ticker.upper(), limit),
    ).fetchall()
    return [r["id"] for r in rows]


def vector_ranking(rows, query_vec: np.ndarray, limit: int = 50) -> list[int]:
    with_vec = [r for r in rows if r["embedding"] is not None]
    if not with_vec:
        return []
    matrix = np.stack([np.frombuffer(r["embedding"], dtype=np.float32) for r in with_vec])
    scores = matrix @ query_vec
    order = np.argsort(-scores)[:limit]
    return [with_vec[i]["id"] for i in order]


def fuse(rankings: list[list[int]], k: int = RRF_K) -> list[int]:
    """Reciprocal rank fusion of several rankings of chunk ids."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking, 1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda cid: -scores[cid])


def search(conn, embedder, ticker: str, question: str, k: int = 10,
           mode: str = "hybrid") -> list[dict]:
    """
    Top-k chunks for a question. mode is "hybrid", "vector" or "keyword";
    the latter two exist so eval_rag.py can compare them.
    """
    rows = conn.execute(CHUNK_SQL, (ticker.upper(),)).fetchall()
    by_id = {r["id"]: r for r in rows}

    rankings = []
    if mode in ("hybrid", "vector"):
        rankings.append(vector_ranking(rows, embedder.embed_query(question)))
    if mode in ("hybrid", "keyword"):
        rankings.append(keyword_ranking(conn, ticker, question))

    ranked = fuse(rankings) if len(rankings) > 1 else (rankings[0] if rankings else [])
    out = []
    for cid in ranked[:k]:
        r = by_id[cid]
        out.append({"id": cid, "text": r["text"], "section": r["section"],
                    "form": r["form"], "filing_date": r["filing_date"], "url": r["url"]})
    return out


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def stats(conn) -> None:
    rows = conn.execute("""
        SELECT f.ticker, f.form, COUNT(DISTINCT f.id) AS filings, COUNT(c.id) AS chunks,
               MIN(f.filing_date) AS first, MAX(f.filing_date) AS last
        FROM filings f
        LEFT JOIN sections s ON s.filing_id = f.id
        LEFT JOIN chunks c ON c.section_id = s.id
        GROUP BY f.ticker, f.form ORDER BY f.ticker, f.form
    """).fetchall()
    if not rows:
        print("Database is empty. Run: python store.py ingest AAPL")
        return
    print(f"{'ticker':<7}{'form':<6}{'filings':>8}{'chunks':>8}  range")
    for r in rows:
        print(f"{r['ticker']:<7}{r['form']:<6}{r['filings']:>8}{r['chunks']:>8}  "
              f"{r['first']} -> {r['last']}")


def main():
    ap = argparse.ArgumentParser(description="Filing store: ingest, stats, search")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_in = sub.add_parser("ingest")
    p_in.add_argument("ticker")
    p_in.add_argument("--filings", type=int, default=8)
    sub.add_parser("stats")
    p_s = sub.add_parser("search")
    p_s.add_argument("ticker")
    p_s.add_argument("question")
    p_s.add_argument("--k", type=int, default=5)
    p_s.add_argument("--mode", choices=("hybrid", "vector", "keyword"), default="hybrid")
    args = ap.parse_args()

    conn = connect()
    if args.cmd == "ingest":
        ingest(args.ticker, args.filings, conn)
    elif args.cmd == "stats":
        stats(conn)
    else:
        hits = search(conn, Embedder(), args.ticker, args.question, args.k, args.mode)
        if not hits:
            sys.exit(f"No results. Has {args.ticker} been ingested?")
        for h in hits:
            print(f"[{h['id']}] {h['filing_date']} {h['form']} {h['section']}")
            print(f"    {h['text'][:300]}\n")


if __name__ == "__main__":
    main()
