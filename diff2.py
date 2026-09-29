"""
Diff the same Item across two consecutive filings.

Deliberately NOT a character-level diff. Filers re-wrap lines, change a comma,
or swap "fiscal 2025" for "fiscal 2026" throughout -- a raw difflib output is
90% noise. What matters to an investor is paragraph-level:

    ADDED    -> a risk that did not exist last year
    REMOVED  -> a risk management quietly stopped disclosing (often the more
                interesting signal, and the one nobody reads for)
    MODIFIED -> same risk, changed language (hedging got stronger/weaker)

Three metrics are available, kept side by side so improvement claims can be
measured rather than asserted (see README "Threshold provenance"):

    char   difflib.SequenceMatcher. The original. Retained as the baseline
           because it is the thing the others are measured against.
    token  Jaccard over content words. Robust to the passive-to-active
           rewrites filers do wholesale, where char similarity inverts.
    idf    token overlap weighted by corpus-derived rarity. Production
           default: common filing formula loses weight automatically, with
           no hand-maintained phrase list.

Matching is GLOBAL, not greedy. Greedy matching lets an early paragraph claim
a counterpart that a later paragraph needed more, and the error cascades.
Hungarian assignment picks the pairing that maximises total similarity across
the whole section at once. On the AAPL FY2024->FY2025 pair this changed the
answer: an intro paragraph scored 0.333 against an unrelated supply-shortage
conclusion, higher than the 0.283 of its own genuine rewrite, and only global
assignment resolved it correctly.
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
# The token metric returned identical buckets (4 added / 13 removed /
# 46 modified) across floors 0.20-0.30 and degraded outside that band, so 0.25
# is the middle of the stable region. The idf metric runs on a different scale
# and has its own floor below. Re-run tune.py before trusting either beyond
# Apple.
MATCH_FLOOR = 0.25
IDF_MATCH_FLOOR = 0.12
MODIFIED_CEILING = 0.97

METRICS = ("char", "token", "idf")

DEFAULT_FLOORS = {
    "char": 0.30,
    "token": MATCH_FLOOR,
    "idf": IDF_MATCH_FLOOR,
}

# Filing formula that carries no topic signal. Kept ONLY as stopwords for the
# plain token metric; the idf metric discovers these weights itself and needs
# no list. An earlier attempt to strip whole boilerplate PHRASES before
# comparing is documented in the README as a failure -- it was all-or-nothing,
# gutted the paragraphs it targeted, and its unit test concealed that.
STOPWORDS = frozenset(
    """
    the a an and or of to in on for with as at by from that this these those
    is are was were be been being can could may might will would shall should
    it its their his her they them we our us you your such any all other
    more most no not than then there here which who whom whose what when
    where how if but so because however also
    """.split()
)

_WORD = re.compile(r"[a-z]+")


def split_paragraphs(text: str, min_chars: int = 200) -> list[str]:
    """
    Split into paragraphs, dropping fragments.

    Short lines in a filing are almost always headings, page numbers, or
    orphaned clauses from the HTML flattening -- they create false diffs.

    KNOWN BUG: a fixed cutoff is not neutral. A filer adding three words can
    push a paragraph across it in one filing but not the other, leaving its
    counterpart absent from the candidate pool. See boundary.py and the README.
    """
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if len(p.strip()) >= min_chars]


def _tokens(text: str) -> set[str]:
    """Content words only, lowercased, deduplicated."""
    return {w for w in _WORD.findall(text.lower()) if w not in STOPWORDS and len(w) > 2}


def token_similarity(a: str, b: str) -> float:
    """
    Jaccard overlap of content words.

    Insensitive to word order, which is the tradeoff -- acceptable here because
    two risk paragraphs sharing most of their content vocabulary are about the
    same risk in practice.
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def char_similarity(a: str, b: str) -> float:
    """
    Character-level ratio. The original metric, retained as the baseline.

    On real filings this is not merely noisy but inverted: a lightly rewritten
    pair scored 0.030 while two unrelated risks scored 0.319.
    """
    return SequenceMatcher(None, a, b).ratio()


SIMILARITY = {"token": token_similarity, "char": char_similarity}


def build_similarity(metric: str, paragraphs: list[str]):
    """
    Return a two-argument similarity function for the chosen metric.

    The idf metric needs the whole corpus to compute weights, so it cannot be
    a plain module-level function like the other two.
    """
    if metric == "idf":
        from idf import build_idf, weighted_similarity

        weights = build_idf(paragraphs)
        return lambda a, b: weighted_similarity(a, b, weights)
    return SIMILARITY[metric]


def _match_optimal(old_paras, new_paras, sim_fn, floor):
    """Hungarian assignment over the full similarity matrix."""
    matrix = np.zeros((len(new_paras), len(old_paras)))
    for i, new_p in enumerate(new_paras):
        for j, old_p in enumerate(old_paras):
            matrix[i, j] = sim_fn(old_p, new_p)

    rows, cols = linear_sum_assignment(-matrix)
    return {
        int(i): (int(j), float(matrix[i, j]))
        for i, j in zip(rows, cols)
        if matrix[i, j] >= floor
    }


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
    metric: str = "idf",
    floor: float | None = None,
    ceiling: float = MODIFIED_CEILING,
) -> dict:
    """
    Compare one Item across two filings.

    floor defaults to the tuned value for the chosen metric, because the three
    metrics run on different scales and a shared number would be meaningless.
    """
    if metric not in METRICS:
        raise ValueError(f"metric must be one of {METRICS}, got {metric!r}")
    if floor is None:
        floor = DEFAULT_FLOORS[metric]

    old_paras = split_paragraphs(old_text, min_chars)
    new_paras = split_paragraphs(new_text, min_chars)

    # Weights come from both filings together, so a term is judged common or
    # rare relative to this comparison rather than an external corpus.
    sim_fn = build_similarity(metric, old_paras + new_paras)

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
            "matcher": "hungarian" if _HAVE_SCIPY else "greedy",
        },
    }
