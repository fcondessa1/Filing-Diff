"""
Diff the same Item across two consecutive filings.

Deliberately NOT a character-level diff. Filers re-wrap lines, change a comma,
or swap "fiscal 2025" for "fiscal 2026" throughout -- a raw difflib output is
90% noise. What matters to an investor is paragraph-level:

    ADDED    -> a risk that did not exist last quarter
    REMOVED  -> a risk management quietly stopped disclosing (often the most
                interesting signal, and the one nobody reads for)
    MODIFIED -> same risk, changed language (hedging got stronger/weaker)

We match paragraphs by similarity rather than position, because a single
inserted paragraph would otherwise shift everything below it and report the
whole section as changed.
"""

import re
from difflib import SequenceMatcher

# Below this, two paragraphs are unrelated. Above MODIFIED_CEILING, the change
# is cosmetic (a date, a rounded number) and not worth surfacing.
MATCH_FLOOR = 0.55
MODIFIED_CEILING = 0.97


def split_paragraphs(text: str, min_chars: int = 200) -> list[str]:
    """
    Split into paragraphs, dropping fragments.

    Short lines in a filing are almost always headings, page numbers, or
    orphaned clauses from the HTML flattening -- they create false diffs.
    """
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if len(p.strip()) >= min_chars]


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def diff_sections(old_text: str, new_text: str, min_chars: int = 200) -> dict:
    """
    Compare one Item across two filings.

    Greedy best-match: for each new paragraph, find its closest surviving
    counterpart in the old filing. Good enough at this scale (a Risk Factors
    section is 50-150 paragraphs) and keeps the logic inspectable. If you
    later swap in embeddings, keep this as the baseline to compare against --
    that comparison is a strong thing to write up.
    """
    old_paras = split_paragraphs(old_text, min_chars)
    new_paras = split_paragraphs(new_text, min_chars)

    unmatched_old = list(range(len(old_paras)))
    added, modified = [], []

    for new_p in new_paras:
        best_idx, best_score = None, 0.0
        for i in unmatched_old:
            score = _similarity(old_paras[i], new_p)
            if score > best_score:
                best_idx, best_score = i, score

        if best_score < MATCH_FLOOR:
            added.append(new_p)
        else:
            unmatched_old.remove(best_idx)
            if best_score < MODIFIED_CEILING:
                modified.append(
                    {
                        "old": old_paras[best_idx],
                        "new": new_p,
                        "similarity": round(best_score, 3),
                    }
                )

    removed = [old_paras[i] for i in unmatched_old]

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
        },
    }
