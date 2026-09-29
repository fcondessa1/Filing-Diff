# Filing Diff

Tracks what changes in the SEC disclosures of companies I hold.

Public companies rewrite their Risk Factors every year, and the edits are where
the information is. A risk that gets *added* is management naming a new threat.
A risk that gets quietly *removed* is often the more interesting signal, and
effectively nobody reads for it. This tool does that reading and reports only
the deltas.

It does not predict prices. It compresses reading.

## Status

- [x] EDGAR ingestion with rate limiting
- [x] Item extraction (1A Risk Factors, 7 MD&A) surviving TOC and cross-reference collisions
- [x] Paragraph-level semantic diff (added / removed / modified)
- [x] Similarity metric selected by measurement against real filings, not assumption
- [x] Thresholds tuned by sweep and cross-metric agreement
- [ ] `min_chars` boundary asymmetry — known open bug, see Open questions
- [ ] LLM summarisation of deltas, with citations to source text
- [ ] RAG index across filings for cross-quarter questions
- [ ] Weekly digest for my watchlist

## Setup

```bash
pip install -r requirements.txt
```

Open `edgar.py` and set `USER_AGENT` to your real name and email. EDGAR returns
403 to anonymous clients — a documented requirement, not a scraping workaround.

```bash
python edgar.py             # smoke test: lists AAPL's recent filings
python run_diff.py AAPL 1A  # diff the two most recent 10-K Risk Factors
```

## Architecture

```
edgar.py      ticker -> CIK -> filing list -> raw HTML
sections.py   HTML -> plain text -> {Item 1A, Item 7}
idf.py        corpus-derived term weights used by the production metric
diff2.py      two versions of an Item -> added / removed / modified
run_diff.py   CLI tying the above together
```

Diagnostics — these produced the design decisions below and are part of the
project, not scaffolding:

```
tune.py       threshold sweeps across all three similarity metrics
agreement.py  do two metrics agree on the partition, or only on the counts?
boundary.py   find paragraphs the length filter drops asymmetrically
cost.py       token and dollar cost model for the summarisation layer
diff.py       the original character-similarity version, kept as the baseline
```

`diff.py` is retained deliberately. Every claim that the current metric is
better is measured against it.

## Engineering notes

Each of these was found by running the tool against real Apple 10-Ks (FY2024 vs
FY2025), not by reasoning ahead of time. They are in the order they surfaced,
because each fix exposed the next problem.

**The table-of-contents collision.** Every filing contains each Item heading at
least twice: once in the TOC, once as the real heading. Taking the first match
yields ~40 characters of dot leaders. Solved by generating every candidate
(start, end) pair and keeping the longest enclosed span, discarding anything
under 1000 characters as a TOC artifact.

**Longest-span then lost to a cross-reference.** That fix created a new failure.
Apple's forward-looking-statements preamble contains "...described in Item 1A of
this Form 10-K under the heading Risk Factors...", an inline mention sitting
*before* the real section. It produced an even longer span and won, inflating
Item 1A to 85,000 characters. Fixed by requiring the heading to begin a line and
rejecting matches followed by cross-reference clauses. A heuristic being correct
on the case that motivated it is not evidence that it is correct.

**Paragraph structure did not survive HTML flattening.** The diff operates on
paragraphs, and the splitter looked for blank lines. BeautifulSoup emits only a
single newline between text nodes, and Apple builds paragraphs from `<div>` and
`<span>` rather than `<p>` — so 85,000 characters collapsed into three
28,000-character blobs. Comparing blobs is meaningless: they differ somewhere,
similarity falls below any floor, and the same text is reported as both added
and removed. Fixed by inserting explicit breaks after block-level elements
*before* flattening. Paragraph count went from 3 to 91.

**Character similarity ranked unrelated pairs above genuine matches.** Apple's
FY2025 filing rewrote nearly every risk factor to strip "There can be no
assurance that..." constructions. `difflib.SequenceMatcher` scored a lightly
rewritten pair at **0.030** while scoring two unrelated risks at **0.319** — the
metric was inverted, not merely noisy. Replaced with token overlap (Jaccard over
content words), which scored the same pairs at 0.634 and 0.000. Greedy matching
was replaced with Hungarian assignment (`scipy.optimize.linear_sum_assignment`)
at the same time: greedy lets an early paragraph claim a counterpart a later one
needed more, and the error cascades.

**Boilerplate inflated similarity between unrelated risks.** Threshold tuning
surfaced two borderline pairs: an intro paragraph against an unrelated supply
conclusion at **0.333**, and the same intro against its actual rewrite at
**0.283**. The false pair scored higher, because both close with Apple's stock
formula "business, results of operations, financial condition and stock price",
which appears in most paragraphs and carries no topic signal.

**The first fix for that failed, and the unit test concealed it.** Stripping a
hand-maintained list of boilerplate phrases is all-or-nothing. Section intros
are ~90% formula, so stripping gutted them and scores collapsed to 0.059 —
correct ordering, unusable magnitude. Adding a fallback (skip stripping when it
removes >45% of tokens) made stripping a no-op for exactly the paragraphs that
needed it. The unit test used *truncated* paragraphs that stayed under the
fallback threshold, so it passed. Running against real filings showed the
near-miss scores unchanged at 0.333 and 0.283: the fix had done nothing. A test
that passes on unrepresentative data is worse than no test, because it
manufactures confidence. That code has been removed rather than kept as dead
weight; this note is the record of it.

**IDF weighting replaced it.** Down-weight common terms instead of deleting
them, with weights derived from the filings being compared. No cliff, and
nothing hand-listed, so it adapts to any filer's house style. The lowest-weight
terms it derived unprompted were `business`, `operations`, `results`,
`materially`, `adversely` — Apple's formula, discovered rather than specified.
The inversion resolved: false pair 0.024, true pair 0.066. The scale changes
completely, so the previous floor was meaningless and had to be re-swept.

**Metric disagreement located a bug in neither metric.** Token@0.25 and
IDF@0.12 produced identical counts (4 added / 13 removed / 46 modified).
Identical counts do not prove identical partitions, so `agreement.py` compared
set membership: 95.7%, with four disagreements. Two were a *swap* — token called
the intro paragraph modified and the supply conclusion added; IDF said the
reverse. A swap means neither metric is wrong; both are being handed an
impossible choice. The cause was upstream: the supply-shortage paragraph is
**197 characters** in FY2024 and **210** in FY2025 (Apple added "and stock
price"), straddling the `min_chars=200` filter. The old version was dropped, so
the new one had no true counterpart and each metric guessed differently.

## Threshold provenance

Not eyeballed. `tune.py` sweeps each metric and reports how the buckets move.

| metric | stable floor band | added | removed | modified |
|---|---|---|---|---|
| char  | 0.25–0.35 | 17 | 26 | 35 |
| token | 0.20–0.25 |  4 | 13 | 46 |
| idf   | 0.10–0.15 |  4 | 13 | 46 |

About 30 phantom add/remove pairs eliminated by changing the metric alone. Two
metrics with different failure modes converging on the same partition is the
strongest evidence available short of hand-labelling every paragraph.

The IDF band below 0.10 looks like a plateau but is degenerate: it reports 0
added and 9 removed against 91 old / 82 new paragraphs, and 91 − 82 = 9. Every
new paragraph matched something, which is the maximum possible pairing rather
than a good one.

## Cost

The diff runs first, so the model never sees a whole filing — only the changed
paragraphs. For the AAPL run (63 changes, ~46k input / ~7.6k output tokens),
summarisation costs roughly $0.02–$0.33 per filing depending on model tier, or a
few dollars a year for a 20-ticker watchlist of annual filings. `cost.py` holds
the assumptions.

Worth stating plainly: diffing first does **not** reduce token cost versus
sending both whole sections (~46k vs ~34k tokens). Modified paragraphs are sent
twice, and 63 separate calls carry 63 copies of the instructions. The diff buys
output quality and traceability — each claim cites one specific paragraph pair —
not tokens.

## Open questions

- **`min_chars` boundary asymmetry (open bug).** A fixed length cutoff is not
  neutral: a filer adding three words can push a paragraph across it in one
  filing but not the other. `boundary.py` detects these. Lowering the cutoff
  readmits headings and page-number fragments, which generate their own false
  diffs, so it needs its own sweep rather than an arbitrary value.
- **Embeddings.** The intro-paragraph case is the ceiling of lexical matching:
  two paragraphs recognisable as the same by *meaning* while sharing little
  vocabulary. Worth measuring against the current metric, keeping `diff.py` and
  the token metric as baselines.
- **10-Q numbering** differs from 10-K (MD&A is Part I Item 2). Currently a
  lookup table; may need per-form logic.
- **Generalisation.** Everything above was tuned against one filer. The
  thresholds should not be trusted beyond Apple until swept against others.

## Limitations

This is an information-summarisation tool, not investment advice. Disclosure
changes are one input among many, LLM summaries can misrepresent source text,
and the thresholds are validated against a single filer. Every summary should
link back to the underlying filing text so claims can be checked against the
original.
