"""
Diff the same Item across two consecutive filings.

Deliberately NOT a character-level diff. Filers re-wrap lines, change a comma,
or swap "fiscal 2025" for "fiscal 2026" throughout -- a raw difflib output is
90% noise. What matters to an investor is paragraph-level:

    ADDED    -> a risk that did not exist last quarter
    REMOVED  -> a risk management quietly stopped disclosing (often the most
                interesting signal, and the one nobody reads for)
    MODIFIED -> same risk, changed language (hedging got stronger/weaker)

Two design decisions, both forced by real filings (see README engineering
notes for how they were found):

1. Similarity is TOKEN-based, not character-based. Apple's FY2025 10-K
   rewrote nearly every risk factor to strip "There can be no assurance
   that..." constructions. Character-level SequenceMatcher scored those
   rewrites near 0.4 and reported them as an unrelated add plus an unrelated
   removal. Comparing bags of content words instead keeps the topic match
   intact when only the phrasing moved.

2. Matching is GLOBAL, not greedy. Greedy matching lets an early paragraph
   claim a counterpart that a later paragraph needed more, and the error
   cascades. Hungarian assignment picks the pairing that maximises total
   similarity across the whole section at once.
"""

import re
from difflib import SequenceMatcher

try:
    from scipy.optimize import linear_sum_assignment
    import numpy as np

    _HAVE_SCIPY = True
except ImportError:  # pragma: no cover - graceful fallback
    _HAVE_SCIPY = False

# Below MATCH_FLOOR, two paragraphs are unrelated. Above MODIFIED_CEILING, the
# change is cosmetic (a date, a rounded number) and not worth surfacing.
#
# TUNED, not guessed. Method: tune.py sweep on AAPL 10-K FY2024 -> FY2025.
# Token metric returned identical buckets (4 added / 13 removed / 48 modified)
# across floors 0.20-0.30, and degraded outside that band -- 0.15 force-matched
# distinct risks, 0.40+ began splitting rewrites into phantom add/remove pairs.
# 0.25 is the middle of the stable region. Confirmed by eye: a genuine rewrite
# of the section-intro paragraph scores 0.283 and is correctly captured at 0.25
# but lost at 0.35.
#
# Re-run tune.py against a second filer before trusting this beyond Apple.
MATCH_FLOOR = 0.25
MODIFIED_CEILING = 0.97

# Legal/filing boilerplate carries no topic signal but appears in every
# paragraph, which inflates similarity between unrelated risks.
STOPWORDS = frozenset(
    """
    the a an and or of to in on for with as at by from that this these those
    is are was were be been being can could may might will would shall should
    it its their his her they them we our us you your company companys
    such any all other others more most no not than then there here which who
    whom whose what when where how if but so because however addition also
    including include includes included time times various certain
    """.split()
)

_WORD = re.compile(r"[a-z]+")

# Recurring formulae that appear in a majority of risk paragraphs and carry no
# topic signal. Found via tune.py near-miss inspection: an intro paragraph and
# an unrelated supply-shortage conclusion scored 0.333 -- higher than a genuine
# rewrite pair at 0.283 -- purely because both close with Apple's standard
# "business, results of operations, financial condition and stock price" tail.
BOILERPLATE = [
    re.compile(
        r"business,?\s+(reputation,?\s+)?results of operations,?\s+"
        r"(and\s+)?financial condition(,?\s+and stock price)?",
        re.IGNORECASE,
    ),
    re.compile(r"materially\s+(and\s+)?adversely\s+affect", re.IGNORECASE),
    re.compile(r"there can be no assurance", re.IGNORECASE),
    re.compile(r"could have a material adverse effect", re.IGNORECASE),
]


def strip_boilerplate(text: str) -> str:
    for pattern in BOILERPLATE:
        text = pattern.sub(" ", text)
    return text


def split_paragraphs(text: str, min_chars: int = 200) -> list[str]:
    """
    Split into paragraphs, dropping fragments.

    Short lines in a filing are almost always headings, page numbers, or
    orphaned clauses from the HTML flattening -- they create false diffs.
    """
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if len(p.strip()) >= min_chars]


def _tokens(text: str, strip: bool = True) -> set[str]:
    """Content words only, lowercased, deduplicated."""
    if strip:
        text = strip_boilerplate(text)
    return {w for w in _WORD.findall(text.lower()) if w not in STOPWORDS and len(w) > 2}


# When stripping removes more than this fraction of a paragraph's content
# words, the paragraph was mostly formula and stripping has destroyed signal
# rather than cleaned it. An absolute token count doesn't work here: section
# intros are short AND boilerplate-heavy, so they clear any low count while
# still being gutted.
MAX_STRIP_FRACTION = 0.45


def token_similarity(a: str, b: str) -> float:
    """
    Jaccard overlap of content words, with filing boilerplate removed.

    Robust to rewording, sentence reordering, and the passive-to-active
    rewrites filers do wholesale. Insensitive to word order, which is the
    tradeoff -- acceptable here because two risk paragraphs sharing most of
    their content vocabulary are about the same risk in practice.

    Stripping is skipped when it would leave a paragraph with almost nothing.
    Boilerplate-dominated paragraphs (section intros especially) are ~90%
    formula, and stripping collapsed a genuine intro-vs-intro match from 0.283
    to 0.059 -- correct ordering, unusable magnitude. Falling back preserves
    the comparison for exactly the paragraphs where stripping backfires.
    """
    raw_a, raw_b = _tokens(a, strip=False), _tokens(b, strip=False)
    ta, tb = _tokens(a), _tokens(b)

    def gutted(stripped, raw):
        return bool(raw) and (1 - len(stripped) / len(raw)) > MAX_STRIP_FRACTION

    if gutted(ta, raw_a) or gutted(tb, raw_b):
        ta, tb = raw_a, raw_b

    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def char_similarity(a: str, b: str) -> float:
    """Original character-level metric. Kept as the baseline to measure against."""
    return SequenceMatcher(None, a, b).ratio()


SIMILARITY = {"token": token_similarity, "char": char_similarity}


def _match_optimal(old_paras, new_paras, sim_fn, floor):
    """Hungarian assignment over the full similarity matrix."""
    matrix = np.zeros((len(new_paras), len(old_paras)))
    for i, np_ in enumerate(new_paras):
        for j, op in enumerate(old_paras):
            matrix[i, j] = sim_fn(op, np_)

    rows, cols = linear_sum_assignment(-matrix)
    pairs = {int(i): (int(j), float(matrix[i, j])) for i, j in zip(rows, cols)
             if matrix[i, j] >= floor}
    return pairs


def _match_greedy(old_paras, new_paras, sim_fn, floor):
    """Fallback when scipy is unavailable. Order-dependent, hence inferior."""
    available = list(range(len(old_paras)))
    pairs = {}
    for i, new_p in enumerate(new_paras):
        best_j, best_score = None, 0.0
        for j in available:
            score = sim_fn(old_paras[j], new_p)
            if score > best_score:
                best_j, best_score = j, score
        if best_j is not None and best_score >= floor:
            available.remove(best_j)
            pairs[i] = (best_j, best_score)
    return pairs


def diff_sections(
    old_text: str,
    new_text: str,
    min_chars: int = 200,
    metric: str = "token",
    floor: float = MATCH_FLOOR,
    ceiling: float = MODIFIED_CEILING,
) -> dict:
    """Compare one Item across two filings."""
    old_paras = split_paragraphs(old_text, min_chars)
    new_paras = split_paragraphs(new_text, min_chars)
    sim_fn = SIMILARITY[metric]

    matcher = _match_optimal if _HAVE_SCIPY else _match_greedy
    pairs = matcher(old_paras, new_paras, sim_fn, floor)

    added, modified = [], []
    matched_old = set()

    for i, new_p in enumerate(new_paras):
        if i not in pairs:
            added.append(new_p)
            continue
        j, score = pairs[i]
        matched_old.add(j)
        if score < ceiling:
            modified.append(
                {"old": old_paras[j], "new": new_p, "similarity": round(score, 3)}
            )

    removed = [p for j, p in enumerate(old_paras) if j not in matched_old]

    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "stats": {
            "old_paragraphs": len(old_paras),
            "new_paragraphs": len(new_paras),
            "added": len(added),
            "removed": len(removed),
            "modified": len(modified),
            "metric": metric,
            "floor": floor,
        },
    }