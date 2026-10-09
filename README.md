# Filing Diff

Tracks what changes in the SEC disclosures of companies I hold.

Public companies rewrite their Risk Factors every year, and the edits are where
the information is. A risk that gets *added* is management naming a new threat.
A risk that gets quietly *removed* is often the more interesting signal, and
effectively nobody reads for it. This tool does that reading and reports only
the deltas.

It does not predict prices. It compresses reading.

## What it found

First real run: Apple 10-K, FY2024 → FY2025, Item 1A (Risk Factors).
Every flagged removal was checked by hand against both filings.

**The tool flagged 12 removals. Two were material removals.**

| verdict | count |
|---|---|
| Merged into a consolidated paragraph, nothing lost | 3 |
| Partially removed (specific language dropped) | 5 |
| Removed — boilerplate / summary sentence | 2 |
| **Removed — material risk** | **2** |

Three of the five partial removals were first marked by hand as merged,
reworded or scattered. The LLM step (below) judged them partial and named
what was missing; searching the FY2025 10-K confirmed the missing language
appears nowhere in the filing, and the hand verdicts were corrected.

The material removals:

- **Retail operations** — the standalone risk covering store construction
  costs, retail leases, retail inventory and retail partners is gone. Retail
  stores now appear only in passing, inside the natural-disasters paragraph.
- **Digital rights management** — the risk that content providers could
  require DRM or security technology the Company might not be able to develop
  or license. The closest surviving text is about content licensing terms, a
  separate risk that was already in the FY2024 filing.

The partial removals, and what was dropped:

- **App Store commission.** The DMA content survives almost word for word, but
  the description of the commission and the explicit risk of "reductions in the
  rate of the commission … or if the rate of the commission is otherwise
  narrowed in scope or eliminated" do not appear in Item 1A.
- **Seasonality.** The single-product concentration risk moved into the
  gross-margins paragraph, where "single product" became "single product
  **category**". The sentence about higher first-quarter sales from holiday
  demand is no longer in Item 1A.
- **Payment cards.** Folded into the privacy paragraph, but the risk of losing
  the ability to process payment cards for failing industry security
  standards is gone.
- **Single-source suppliers.** Folded into the manufacturing-concentration
  paragraph, but the list of ways manufacturing or logistics "or transit to
  final destinations" can be disrupted (disasters, IT failures, labour
  issues, geopolitical tensions) is gone.
- **Manufacturing equipment and supplier prepayments.** Credit risk on
  prepayments survives in the receivables paragraph, but the risk that
  equipment held at suppliers and prepayments may not be recoverable if a
  supplier gets into financial trouble is gone.

The last three were confirmed by searching the whole FY2025 10-K for the
dropped wording. The first two were checked within Item 1A only; that
language may have moved elsewhere in the 10-K.

**Why the raw count was wrong.** Apple restructured Item 1A this year and
combined several paragraphs into fewer, longer ones. The matcher pairs
paragraphs one-to-one, so when three old paragraphs merge into one new
paragraph, one of the three gets matched and the other two show up as
removals, even though their text survives word for word. See "Merges are
invisible to a one-to-one matcher" below.

Full verdicts, with both versions of each paragraph:
[`results/aapl_fy2025_verification.txt`](results/aapl_fy2025_verification.txt).

## Status

- [x] EDGAR ingestion with rate limiting
- [x] Item extraction (1A Risk Factors, 7 MD&A) surviving TOC and cross-reference collisions
- [x] Paragraph-level semantic diff (added / removed / modified)
- [x] Similarity metric selected by measurement against real filings, not assumption
- [x] Thresholds tuned by sweep and cross-metric agreement
- [x] `min_chars` tuned to 130 — boundary asymmetry resolved
- [x] Removals verified by hand against source filings (AAPL FY2025)
- [ ] Merge / split detection built into the diff itself
- [x] LLM summarisation of deltas, with every quote checked against the source text
- [x] Question answering across filings: hybrid search over SQLite, cited and checked answers
- [x] Weekly digest for my watchlist, run on a schedule by GitHub Actions

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

For LLM summaries, set an Anthropic API key in your environment (never in
the code):

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
python summarise.py AAPL 1A --limit 5   # cheap first run
python summarise.py AAPL 1A             # writes results/aapl_1a_digest.md
```

To ask questions across filings, index them first. Embeddings run locally
(no key, no cost); the model downloads once, about 130 MB:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python store.py ingest AAPL                 # last 8 10-K/10-Q filings
python eval_rag.py AAPL                     # check retrieval first
python ask.py AAPL "What has Apple said about tariffs?"
```

## Architecture

```
edgar.py      ticker -> CIK -> filing list -> raw HTML
sections.py   HTML -> plain text -> {Item 1A, Item 7}
idf.py        corpus-derived term weights used by the production metric
diff2.py      two versions of an Item -> added / removed / modified
run_diff.py   CLI tying the above together
summarise.py  Claude explains each change; code verifies every quote it gives
store.py      SQLite store: filings, sections, chunks, embeddings, full-text index
ask.py        answer questions across filings, each claim checked against its source
eval_rag.py   score keyword, vector and hybrid retrieval before trusting answers
digest.py     weekly: new filings on the watchlist -> checked summaries -> issue
```

Diagnostics — these produced the design decisions below and are part of the
project, not scaffolding:

```
tune.py       threshold sweeps across all three similarity metrics
agreement.py  do two metrics agree on the partition, or only on the counts?
boundary.py   find paragraphs the length filter drops asymmetrically
verify.py     check whether each "removed" paragraph survives elsewhere
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

## LLM summaries and grounding

`summarise.py` sends each change to Claude (Haiku 4.5 by default) with
structured output: a one-sentence summary, a materiality rating, and 1–3
quotes copied from the filing as evidence. The model's word is not taken for
the quotes. The code checks each one verbatim against the filing it was
attributed to:

| status | meaning |
|---|---|
| VERIFIED | every quote appears in the stated filing |
| PARTIAL | some quotes found, some not |
| UNSUPPORTED | no quote found, or a quote attributed to the wrong filing |

Unverified summaries stay in the digest, flagged, rather than being dropped,
so the failure rate stays visible. Comparison ignores typography (curly vs
straight quotes, non-breaking spaces) but not wording.

Removed paragraphs that `verify.py` identifies as merge artifacts are skipped,
so the summariser does not restate the diff's own mistake.

**Quote checks catch invented quotes, not wrong conclusions.** On the first
full run, 57 of 63 summaries verified. But five of the twelve rated
high-materiality were wrong, and four of those were contradicted by other
entries in the same digest. The diff labelled paragraphs as REMOVED that Apple
had merged or reworded; the model, shown only the old paragraph, accurately
quoted it and wrote a confident summary of a removal that had not happened.
For example, the digest reported the single-source supplier risk as removed
(high materiality, verified), while another entry quoted the same risk from
the new filing.

**Fix: removals are judged, not trusted.** Each removed paragraph is now sent
with the two paragraphs in the new filing that contain most of its content.
The model must decide whether the risk was removed, moved or reworded, or
partially removed, and a "still disclosed" verdict must quote the new filing.
That quote is checked like any other, so the model cannot claim the text
survived without showing where.

**Result.** The model's verdicts were scored against the hand verification
above, for the 9 removals it judged (the other 3 were merge artifacts and
skipped). The baseline is the diff's label taken at face value, which calls
all 9 removed.

| question | model | diff label alone |
|---|---|---|
| exact verdict (removed / moved / partly removed) | 7/9 | 4/9 |
| was the risk dropped completely? | 7/9 | 4/9 |

None of the four self-contradicting removals from the first run is still
reported as removed.

The 7/9 needs two qualifications:

- **The model also corrected the hand labels.** It first scored 4/9 exact.
  Three of its five disagreements were paragraphs I had marked as merged or
  reworded that the model called partly removed, naming the detail that was
  missing. Searching the FY2025 10-K found none of that wording, so the model
  was right and the labels were changed. Labels were changed only where the
  filing confirmed it; with nine examples it would be easy to tune labels or
  prompt until the score looked good and the score meant nothing.
- **The two remaining misses are different in kind.** One is a model error:
  it treated the new preamble as preserving the old "past financial
  performance should not be considered a reliable indicator" disclaimer,
  which it does not — the shared-boilerplate trap the prompt warns against.
  The other is a definition mismatch. The paragraph on Apple's "ability to
  continually improve its products" was deleted (the hand label), but an
  overlapping paragraph that already existed in FY2024 still covers the risk
  (the model's answer). The two labels answer different questions: "was this
  paragraph deleted?" versus "is this risk still disclosed?"

Nine examples from one filing is too few to call the model accurate. What it
shows is that judging removals against the surviving text stopped the
dangerous error, a still-disclosed risk reported as removed.

Not yet fixed: a mispaired MODIFIED change. The diff matched the old
introduction to an unrelated competition paragraph, and the model summarised
the "change" between them as a high-materiality replacement. Low-similarity
pairs need the same judgment step. Responses are cached
on disk by model, prompt version and change text, so re-runs only pay for new
changes.

## Asking questions across filings

`ask.py` answers a question from the last eight filings (10-Ks and 10-Qs,
Risk Factors and MD&A), for example "what has Apple said about tariffs over
the last two years?"

**Storage is plain SQL.** `store.py` keeps filings, extracted sections and
paragraph-sized chunks in SQLite tables, one file (`data/filings.db`, not
committed). Each chunk stores its embedding, and SQLite's built-in full-text
index (FTS5) covers the same text.

**Retrieval is hybrid, and measured.** Embeddings from a local model
(`BAAI/bge-small-en-v1.5`) find passages that mean the same as the question
("customs duties" finds "tariffs"). Keyword search with BM25 ranking finds
exact terms such as case names. The two rankings are merged by reciprocal
rank fusion, which needs no tuning of how a cosine similarity compares with
a BM25 score. The full-text index uses the Porter stemmer: SQLite's default
tokenizer does not stem, so "import" would not match "imports". Vector search
is a brute-force cosine in numpy, which takes milliseconds at a few thousand
chunks; a vector index would add a dependency without making it faster.

`eval_rag.py` scores the three modes on questions whose answers are known
phrases in Apple's filings, so a hit is a checkable fact. Scores are mean
reciprocal rank (1.0 means the answer was always ranked first):

| question type | keyword | meaning | combined |
|---|---|---|---|
| reworded: worded unlike the filing, e.g. "import duties" (8) | 0.48 | **0.84** | 0.65 |
| exact-term: legal names in the filing, e.g. "Section 232" (4) | **1.00** | 0.62 | 0.88 |
| all 12 | 0.65 | **0.77** | 0.72 |

The first version had only the reworded questions, and on those combined
search lost to meaning search alone: equal-weight fusion let keyword noise
outvote a correct answer only meaning search had found. "How dependent is
Apple on one product?" dropped from rank 1 to rank 9, because "product"
appears in hundreds of paragraphs and keyword search returned 50 noisy
matches. But questions written to avoid the filing's wording cannot show what
keyword search adds, so exact-term questions were added before choosing a
default. Each method then won its own group.

Combined search stays the default. It is never the best, but it is the only
mode that is not the worst on either kind of question, and `ask.py` reads 12
passages, so what matters is whether the answer reaches the top 10, which
both meaning-only and combined achieved on all 12 questions. Meaning-only's
higher MRR rests on four questions that split two each way. Weighting the two
methods differently might help, but tuning a weight on 12 questions would fit
these 12 questions, so it was not done. Twelve questions written by the
person who built the system is a smoke test, not a benchmark.

**Answers are checked the same way as the summaries.** Passages are given to
Claude oldest first, labelled with filing date and form, so it can say when
something changed. Every claim must cite a passage and quote it exactly; the
code checks that the passage was one the model was shown and that the quote
is in it, and says where a misattributed quote really is. The model can
answer "not in sources" instead of stretching unrelated passages into an
answer. As the summariser showed, a verified quote still does not make a
claim true, so the answer lists the passages it rests on.

**Model choice is the defence against omissions.** Haiku and Sonnet were
asked the same question ("what has Apple said about tariffs over the last two
years?") with the same 12 passages, so any difference came from the model.
Every run verified all its claims. But Haiku left out the new tariffs
imposed under Section 122 and Section 301, which were in the passages it was
shown, and ended on the Supreme Court refunds, implying tariffs were being
wound down. Sonnet ended on the latest position in both of two runs and named
Section 301 both times, but Section 122 only once. The same model, prompt and
passages gave different answers from one run to the next, so a single run per
model is not a comparison. A citation check proves what the model said is in
the sources, not that it said everything important. `ask.py` defaults to
Sonnet (about 2.4 cents a question against 0.9) because it omitted less, but
that reduces omissions rather than preventing them. The summariser's 63 calls
per filing stay on Haiku.

Neither model reached back before May 2025, though the database holds the
November 2024 10-K, which did discuss tariffs. Six of the 12 passages were
the same paragraph repeated across six filings, which crowded out the older
material. That is a retrieval problem no model can fix.

**Fix: collapse repeated paragraphs.** Companies carry paragraphs forward
from filing to filing, editing a sentence each time. `ask.py` now retrieves
40 candidates and groups versions of the same paragraph: two passages are
versions when one's content words are at least 80% contained in the other's.
Containment rather than Jaccard, because a paragraph that grows each quarter
still contains its earlier versions while its Jaccard against them falls.
Each group keeps its earliest and latest version, plus any in-between version
that says something neither of those does (e.g. a sentence added one quarter
and dropped later), and the model is told the span: "a version of this
paragraph appears in 6 filings, from the 10-Q filed 2025-05-02 to the 10-Q
filed 2026-07-31". The freed slots go to the next distinct passages. The
retrieval evaluation still measures raw search, so its scores stay
comparable.

The first run with collapsing cut the copies from six to three and brought
in three useful new passages, but four of the twelve slots went to regional
net-sales paragraphs with nothing to do with tariffs. The November 2024
10-K's tariff passages were still missing. They were in the database (an FTS
query for "tariffs" before May 2025 found two), so the question was where
search ranked them. Meaning search put one at 27, inside the 40 candidates;
combined search dropped it to 47, because keyword search had not found it in
its top 50. The keyword query was the cause: "What has Apple said about
tariffs over the last two years?" became `tariffs OR last OR two OR years`,
and paragraphs comparing "the same period last year" swamped the one topic
word. Three changes followed:

- Words that set a question's time range (last, years, recent, quarter…) are
  no longer keyword search terms. The time range is handled by the filing
  dates shown with each passage.
- Each search method keeps 200 results before fusion instead of 50.
- Slots freed by collapsing go only to passages containing a topic word from
  the question. The original top 12 are never filtered.

Checking the query builder also turned up an older bug: words under three
letters were dropped, which removed acronyms such as "AI" and "EU". Two-letter
words written in capitals are now kept.

**Result** on the same question, same model (Sonnet):

| | before | after |
|---|---|---|
| earliest filing in the answer | May 2025 | November 2024 |
| copies of the main tariff paragraph | 6 | 3 |
| off-topic passages | 0 | 0 |
| claims, all verified | 5 | 8 |
| effect of tariffs on results | not mentioned | "partially offset" margin gains in Q3 2025; refunds lifted margins in 2026 |

The answer now opens with the November 2024 10-K ("tensions between
governments, including the U.S. and China, have in the past led to tariffs")
before moving to the 2025 tariffs. The two gross-margin passages it gained
show what tariffs did to Apple's results, not only what they might do, and
they had been crowded out by copies.

That run also lost Section 122, for a reason in the collapsing itself. The
May 2026 version of one paragraph named Section 122 and the July 2026
version Section 301, but the comparison used the diff's tokenizer, which
keeps letters only, so the two versions looked identical and the May one was
dropped. Numbers now count, except four-digit years, which roll forward each
filing without saying anything new. An in-between version is also kept if it
contains a number that no kept version has, since one new section number
changes the meaning without moving a similarity ratio much.

## Weekly digest

`digest.py` runs every Monday on GitHub's servers
(`.github/workflows/weekly-digest.yml`), so nothing has to be left running.
For each ticker in `watchlist.txt` it asks EDGAR for 10-K and 10-Q filings it
has not processed, compares each new filing's Risk Factors with the previous
filing of the same form, runs the same checked pipeline as `summarise.py`
(merge detection, removals judged against surviving text, every quote
verified), commits `results/digests/<date>.md`, and opens a GitHub issue,
which GitHub emails to the repository owner. Filings arrive about once a
quarter per company, so most weeks report nothing new and make no API calls.

The digest is written to be skimmed and is ordered by importance, not by
company. It opens with a table: one row per new filing, a headline, and its
number of high, medium and low-importance changes. Then come all companies'
high-importance changes, each company with a one- or two-sentence story and
one line per change; then the medium ones, folded under each company's name;
then a count of minor wording changes; then filings with nothing new and
risks not repeated (folded), and the cost and verification counts (folded). The
headline and story are written by the model from the already-checked
summaries, not from the filing, so they carry no quotes of their own; a ⚠️
next to a change marks a summary whose quote was not found in the filing.

Design decisions:

- **10-Q is compared with 10-Q, not with the last 10-K.** Many 10-Qs' Risk
  Factors sections list only updates to the annual report, not the full set.
  Diffing it against a 10-K would report every risk factor it does not repeat
  as removed. 10-Qs write this section in three ways (see below); a "no
  material changes" statement is quoted, not diffed.
- **Adding a company does not summarise its history.** A ticker's first run
  records all its listed filings as the starting point. Recording only the
  latest, as the first draft did, would have made the older ones look new
  the following week.
- **Failures are reported and retried.** One ticker failing does not stop
  the others; the error appears in the digest and counts as news, and a
  filing that failed to process is not marked as done, so next week retries
  it.
- **The scheduled job does not install the embedding model.** The digest
  only diffs and summarises, so `requirements-digest.txt` leaves out torch
  and sentence-transformers.

### First run on eight companies: what broke

Everything before the digest was built and tuned on Apple. The first live run
(IONQ, NVDA, OKTA, GOOGL, AMZN, LEU, MSFT, QBTS) was the first test on other
filers. It completed for 4 of 8 companies (NVDA, GOOGL, LEU, MSFT: 128
changes, about 25 cents) and showed three problems, each diagnosed with
`diagnose_extraction.py` against the actual filings before anything was
changed:

| Company | What the run said | What the filing actually contained | Fix |
|---|---|---|---|
| AMZN | no Risk Factors section | the "Item 1A. Risk Factors" heading is a two-row layout table (one empty row that only sets column widths); the extractor dropped every table, so the heading disappeared | keep one-row-of-text tables that start with "Item N" and name no other item, as headings; the table of contents and financial tables are still dropped. Both AMZN 10-Qs now extract (about 61,000 characters each) |
| OKTA, IONQ Q1, QBTS Q1 | no Risk Factors section | a single sentence: "There have been no material changes to the risk factors..." (200 to 700 characters, under the 1,000-character minimum meant to filter out table-of-contents fragments) | the digest reads short sections too and quotes the statement; no API call |
| IONQ Q2, QBTS Q2 | nothing (compared against the "no changes" quarter) | only the updates: "Other than as set forth below, there have been no material changes", then the new risks | when the previous 10-Q was a statement, every risk in the new section is reported as added since last quarter |

My first guess, before the diagnostic, was that all four were table-heading
failures. It was right for one company. The other three were the extractor
working correctly on a form of disclosure I had not seen in Apple's filings.

The summaries had a separate problem: the model was never told whose filing it
was reading, and summarised an NVIDIA risk and a Microsoft risk as "Broadcom
added...". The quotes behind both were verified, so the citation check passed.
It is the same lesson as the removal summaries: a check on quotes cannot catch
a wrong statement built around them. The ticker is now part of the prompt.

The second run (all eight extracting) showed a different kind of noise: the
same risk summarised two or three times. Filers write each risk factor as a
one-sentence bold headline followed by its explanation, and the diff treated
them as separate paragraphs, so IonQ's new risk on semiconductor cyclicality
got one summary for its headline and another for its body, and Alphabet's $40
billion share-sale programme appeared three times. The digest now joins each
headline to the paragraph after it before diffing (`join_fragments` in
`digest.py`), and rejoins sentences split by page breaks, which removes the
NVDA "penalties available" fragment.

The first version of the rule was checked against the real filings
(`check_joining.py`, no API calls) before any summaries were paid for, and
paired five kinds of text wrongly: the section's opening "no material changes"
sentence, subheadings (Microsoft's "Competition in the technology sector"),
Amazon's bullet points, "Table of Contents" page links stuck to the text, and
text from Items 5 and 6. The last was an extraction bug the check exposed:
LEU's 10-Q goes from Item 1A straight to Item 5, and Risk Factors only ended at
Item 1B or 2, so it had been running on into the rest of the filing. After the
fixes:

| Company | Changes before joining | After |
|---|---|---|
| IONQ | 32 | 17 |
| NVDA | 40 | 32 |
| GOOGL | 18 | 16 |
| LEU | 9 | 7 |
| QBTS | 5 | 4 |
| AMZN | 1 | 1 |
| MSFT | 61 | 60 |
| **Total** | **166** | **137 (17% fewer)** |

The rule works from text alone, so it cannot see bold formatting. It still
joins a short closing sentence of one Microsoft risk ("The competitive
pressures described above may cause...") to the start of the next. Both
filings are joined the same way, so this rarely creates a false change, but
reading bold headings from the HTML would be the proper fix. Also still open:
two MSFT rows describe the same wording as added in one and removed in the
other, the mis-paired paragraph problem seen with Apple.

### Hand-checking a second company: NVIDIA

Apple's hand verification showed most "removals" were text merged into other
paragraphs. The same check on NVIDIA (`verify_digest.py`, review file in
`results/nvda_verification.txt`) found a different cause, and a bigger one.

The 9 October digest reported 15 risks removed from NVIDIA's August 2026 10-Q,
9 of them high materiality: demand forecasting, inventory, supply lead times,
competition, crypto mining. The review file shows each removed paragraph next
to the closest paragraphs in the August 10-Q (what the model saw) and in the
latest 10-K. The answer was in the August section's opening sentence:

> Other than the risk factors listed below, there have been no material
> changes from the risk factors previously described under Item 1A of our
> Annual Report on Form 10-K ... and Item 1A of our Quarterly Report on Form
> 10-Q for the fiscal quarter ended April 26, 2026.

August lists only what changed since May, and says the rest still stands.
The 15 were risks updated in May and not updated again:

| Verdict | Count | Evidence |
|---|---|---|
| Not repeated (still stands) | 14 | 10 identical to the 10-K (containment 1.00); 4 were May's updated versions, still standing by the sentence above |
| Partly removed | 1 | the H20 export-licence paragraph was rewritten in August and no longer states the government's expected 15% revenue share |
| Removed | 0 | |

| | Exact verdict | Removed or not |
|---|---|---|
| Diff alone (calls all 15 removed) | 0/15 | 0/15 |
| Model (saw only the August 10-Q) | 3/15 | 4/15 |

The model called 11 of 15 removed. It was never shown the opening sentence or
the earlier filings, so it could not know; this is a design error in the
pipeline, not a model error. The verdicts in this table were written by
Claude, with the evidence for each in the review file, not by me
independently as Apple's were; the deciding evidence is mechanical (identical
text, plus the incorporation sentence).

The fix (`is_updates_only` and `not_repeated` in `digest.py`): when the new
10-Q lists only updates, a paragraph it leaves out is reported as "not
repeated", with its first sentence, and no model call is made. If the filing
does not say whether the previous 10-Q's updates still stand (naming only the
10-K), the digest says that instead of claiming either way. A left-out
paragraph whose closest new paragraph contains at least 40% of it is treated
as rewritten and still judged by the model: that separates the H20 paragraph
(0.46) from the rest (at most 0.33) on this filing, and is a threshold from
one filing, to be checked as more are verified. On the 9 October digest this
turns NVIDIA's 15 removals into 1 judged change and 14 not-repeated lines,
and LEU's 3 "removed" AI risks into not-repeated lines. Microsoft's removal is
untouched: a 10-K lists every risk, so a missing paragraph there can be a real
removal.

Setup: add two repository secrets under Settings → Secrets and variables →
Actions: `ANTHROPIC_API_KEY` and `EDGAR_USER_AGENT` ("Your Name
your.email@example.com"). Then run the workflow once from the Actions tab
with `force_latest` ticked, to see a digest of each ticker's latest filing
straight away.

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

- **Merge and split detection.** The removal count cannot be trusted until
  the diff itself recognises many-to-one and one-to-many edits. `verify.py`
  catches some of these after the fact. A global-containment check would catch
  condensed and scattered content too.
- **`MODIFIED_CEILING` per metric.** 0.97 was carried over from the token
  metric. The two IDF-vs-token ceiling disagreements that went the other way
  (investments; confidential information) have not been resolved.
- **Embeddings.** The intro-paragraph case is the ceiling of lexical matching:
  two paragraphs recognisable as the same by *meaning* while sharing little
  vocabulary. Worth measuring against the current metric, keeping `diff.py` and
  the token metric as baselines.
- **10-Q numbering** differs from 10-K (MD&A is Part I Item 2). Currently a
  lookup table; may need per-form logic.
- **Generalisation.** The diff thresholds were tuned against one filer and
  have not been swept against others. Extraction has now been tested on eight
  more (see "First run on eight companies"); the thresholds have not.

## Limitations

This is an information-summarisation tool, not investment advice. Disclosure
changes are one input among many, LLM summaries can misrepresent source text,
and the thresholds are validated against a single filer. Every summary should
link back to the underlying filing text so claims can be checked against the
original.
