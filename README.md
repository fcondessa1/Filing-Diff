# Filing Diff

Tracks what changes in the SEC disclosures of companies I hold.

Public companies rewrite their Risk Factors and MD&A every quarter, and the
edits are where the information is. A risk that gets *added* is management
naming a new threat. A risk that gets quietly *removed* is often the more
interesting signal, and effectively nobody reads for it. This tool does that
reading and reports only the deltas.

It does not predict prices. It compresses reading.

## Status

- [x] EDGAR ingestion with rate limiting
- [x] Item extraction (1A Risk Factors, 7 MD&A) that survives the TOC collision
- [x] Paragraph-level semantic diff (added / removed / modified)
- [ ] LLM summarisation of deltas, with citations to source text
- [ ] RAG index across all filings for cross-quarter questions
- [ ] Weekly digest for my watchlist

## Setup

```bash
pip install requests beautifulsoup4
```

Then open `edgar.py` and set `USER_AGENT` to your real name and email. EDGAR
returns 403 to anonymous clients — this is a documented requirement, not a
scraping workaround.

```bash
python edgar.py        # smoke test: prints AAPL's recent filings
python test_sections.py
python test_diff.py
```

## Architecture

```
edgar.py      ticker -> CIK -> filing list -> raw HTML
sections.py   HTML -> plain text -> {Item 1A, Item 7}
diff.py       two versions of an Item -> added / removed / modified paragraphs
```

## Engineering notes

Keep this section growing. It is the part that makes the project worth
discussing.

**The table-of-contents collision.** Every filing contains each Item heading
at least twice: once in the TOC, once as the real heading. Searching for the
first match yields ~40 characters of dot leaders. Solved by generating every
candidate (start, end) pair and keeping the longest enclosed span, then
discarding anything under 1000 characters as a TOC artifact.

**Why tables are dropped.** They are almost entirely financial statements.
They wreck the text flow that paragraph splitting depends on, and the numbers
are better pulled from XBRL, which is already structured.

**Why not a character diff.** Filers re-wrap lines and swap fiscal-year
references throughout, so `difflib` at character level reports the whole
section as changed. Paragraph-level matching by similarity — rather than by
position — means one inserted paragraph doesn't cascade into a false positive
for everything below it.

**Thresholds are guesses so far.** `MATCH_FLOOR = 0.55` and
`MODIFIED_CEILING = 0.97` were set by eyeball. Before trusting the output,
hand-label the deltas for ~10 filing pairs and tune against that. Record what
the numbers were before and after.

## Open questions

- Does `SequenceMatcher` hold up against embedding-based matching, or is the
  extra cost justified? Keep the current version as the baseline to measure.
- Cost and latency per filing once summarisation is added — a 10-K Risk
  Factors section runs 30k–80k tokens.
- 10-Q numbering differs from 10-K (MD&A is Part I Item 2). Currently handled
  by a lookup table; may need per-form logic.
- Failure modes: which filers break extraction, and why.

## Limitations

This is an information-summarisation tool, not investment advice. Disclosure
changes are one input among many, LLM summaries can misrepresent source text,
and the diff thresholds are unvalidated. Every summary should link back to the
underlying filing text so claims can be checked against the original.
