"""
IDF-weighted token similarity: the production metric.

Replaces an earlier hand-maintained boilerplate phrase list, which failed for a
structural reason worth recording. Stripping phrases was all-or-nothing:
paragraphs that were mostly formula (section intros) lost so many tokens that
the code had to fall back to unstripped text, meaning stripping became a no-op
for exactly the paragraphs it was meant to fix. The AAPL near-miss inversion
(0.333 false pair vs 0.283 true pair) survived that "fix" unchanged.

Weighting has no cliff. Every token contributes, scaled by how rare it is in
the filings being compared. "Business", "operations" and "materially" appear in
most paragraphs and approach the floor weight automatically; "ransomware" or
"seasonal" appear once or twice and dominate the comparison. Nothing is
hand-listed, so it adapts to any filer's house style rather than Apple's.
"""

import math
import re

_WORD = re.compile(r"[a-z]+")

STOPWORDS = frozenset(
    """
    the a an and or of to in on for with as at by from that this these those
    is are was were be been being can could may might will would shall should
    it its their his her they them we our us you your such any all other
    more most no not than then there here which who whom whose what when
    where how if but so because however also
    """.split()
)


def tokens(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in STOPWORDS and len(w) > 2]


def build_idf(paragraphs: list[str]) -> dict[str, float]:
    """
    Inverse document frequency over the paragraphs being compared.

    Smoothed by +0.1 so a token appearing in every paragraph gets a small
    positive weight rather than exactly zero. It still carries a little
    information, and zeroing creates its own edge cases with short paragraphs.
    """
    n = len(paragraphs)
    doc_freq: dict[str, int] = {}
    for p in paragraphs:
        for tok in set(tokens(p)):
            doc_freq[tok] = doc_freq.get(tok, 0) + 1
    return {tok: math.log((n + 1) / (df + 1)) + 0.1 for tok, df in doc_freq.items()}


def weighted_similarity(a: str, b: str, idf: dict[str, float]) -> float:
    """
    Weighted Jaccard: shared IDF mass over total IDF mass.

    Reduces to plain Jaccard when all weights are equal, so the simpler metric
    is a special case rather than something discarded.
    """
    ta, tb = set(tokens(a)), set(tokens(b))
    if not ta or not tb:
        return 0.0

    default = 1.0
    shared = sum(idf.get(t, default) for t in ta & tb)
    total = sum(idf.get(t, default) for t in ta | tb)
    return shared / total if total else 0.0
