"""
Tests for summarise.py that run without an API key or network.

A fake client stands in for Claude and returns canned answers, including
deliberately bad ones, so the grounding check can be shown to catch them.

Run: python test_summarise.py
"""

import json
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import summarise
from summarise import check_evidence, collect_changes, summarise_change, write_digest

# Real FY2024 / FY2025 Apple wording, including the curly apostrophe the
# filing uses ("Company’s") -- the model will usually emit a straight one.
OLD = ("The Company’s retail operations are subject to many factors that pose "
       "risks and uncertainties and could adversely impact the Company’s business, "
       "results of operations and financial condition, including macroeconomic "
       "factors that could have an adverse effect on general retail activity.")
NEW_MOD = ("The Company has a minority market share in the global smartphone, "
           "personal computer, tablet and wearables markets.")
OLD_MOD = ("The Company has a minority market share in the global smartphone, "
           "personal computer and tablet markets.")


class FakeClient:
    """Mimics anthropic.Anthropic().messages.create for structured output."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = 0
        self.messages = self

    def create(self, **kwargs):
        assert "output_config" in kwargs, "structured output must be requested"
        self.calls += 1
        answer = self.answers.pop(0)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps(answer))],
            usage=SimpleNamespace(input_tokens=500, output_tokens=90),
        )


def answer(evidence, summary="s", materiality="high"):
    return {"summary": summary, "materiality": materiality,
            "materiality_reason": "r", "evidence": evidence}


def test_grounding():
    removed = {"kind": "removed", "old": OLD, "new": None}
    modified = {"kind": "modified", "old": OLD_MOD, "new": NEW_MOD}

    cases = [
        ("faithful quote, straight apostrophe vs curly in filing",
         removed, [{"source": "old", "quote": "The Company's retail operations are subject to many factors"}],
         "VERIFIED"),
        ("paraphrase presented as a quote",
         removed, [{"source": "old", "quote": "Apple's stores face many economic risks"}],
         "UNSUPPORTED"),
        ("real words, attributed to the wrong filing",
         modified, [{"source": "old", "quote": "tablet and wearables markets"}],
         "UNSUPPORTED"),
        ("one real quote, one invented",
         modified, [{"source": "new", "quote": "tablet and wearables markets"},
                    {"source": "new", "quote": "wearables are a growing priority"}],
         "PARTIAL"),
        ("no evidence at all",
         removed, [], "UNSUPPORTED"),
        ("edge-stripping does not excuse an extra word (\"..., and\")",
         removed, [{"source": "old", "quote": "including macroeconomic factors that could have an adverse effect on general retail activity, and"}],
         "UNSUPPORTED"),
        ("faithful quote, model added a closing full stop (first live run)",
         modified, [{"source": "new", "quote": "personal computer, tablet and wearables markets."}],
         "VERIFIED"),
    ]

    print("=== grounding check ===")
    ok = True
    for label, change, evidence, expected in cases:
        got = check_evidence(change, evidence)["status"]
        ok &= got == expected
        print(f"  {'PASS' if got == expected else 'FAIL'}  {got:<11} {label}")

    wrong = check_evidence(modified, [{"source": "old", "quote": "tablet and wearables markets"}])
    flagged = wrong["evidence"][0]["wrong_source"]
    print(f"  {'PASS' if flagged else 'FAIL'}  wrong-filing quote is labelled as such, not as invented")
    return ok and flagged


def test_cache_and_cost(tmp: Path):
    summarise.CACHE_DIR = tmp / "cache"
    change = {"kind": "modified", "old": OLD_MOD, "new": NEW_MOD}
    good = answer([{"source": "new", "quote": "tablet and wearables markets"}],
                  summary="Apple added wearables to the markets where it holds a minority share.")
    client = FakeClient([good])

    first = summarise_change(client, "claude-haiku-4-5-20251001", change)
    second = summarise_change(client, "claude-haiku-4-5-20251001", change)

    print("\n=== cache ===")
    ok = client.calls == 1 and not first["cached"] and second["cached"]
    print(f"  {'PASS' if ok else 'FAIL'}  second run served from cache (API calls: {client.calls})")

    other = summarise_change(FakeClient([good]), "claude-sonnet-5-5", change)
    ok2 = not other["cached"]
    print(f"  {'PASS' if ok2 else 'FAIL'}  changing the model invalidates the cache")
    return ok and ok2


def test_merge_artifacts_skipped():
    import test_verify as tv
    changes, skipped = collect_changes(tv.OLD, tv.NEW)
    with_merges, _ = collect_changes(tv.OLD, tv.NEW, include_merges=True)
    removed = [c for c in changes if c["kind"] == "removed"]

    print("\n=== merge artifacts ===")
    ok = (len(skipped) == 2 and len(removed) == 1
          and "retail" in removed[0]["old"]
          and len(with_merges) == len(changes) + 2)
    print(f"  {'PASS' if ok else 'FAIL'}  2 merge artifacts skipped; only the genuine "
          f"retail removal is summarised; --include-merges restores them")
    return ok


def test_digest(tmp: Path):
    summarise.RESULTS_DIR = tmp / "results"
    rows = []
    for kind, old, new, ev, mat in [
        ("removed", OLD, None,
         [{"source": "old", "quote": "retail operations are subject to many factors"}], "high"),
        ("modified", OLD_MOD, NEW_MOD,
         [{"source": "new", "quote": "wearables will drive growth"}], "medium"),
    ]:
        change = {"kind": kind, "old": old, "new": new}
        rows.append({**change, **answer(ev, materiality=mat),
                     "check": check_evidence(change, ev),
                     "input_tokens": 500, "output_tokens": 90, "cached": False})

    path = write_digest("AAPL", "1A", "claude-haiku-4-5-20251001", rows, skipped=["x"])
    text = path.read_text()

    print("\n=== digest ===")
    checks = {
        "high-materiality section first": text.index("## High") < text.index("## Medium"),
        "unverified summary is flagged, not hidden": "**[UNVERIFIED]**" in text,
        "missing quote marked ✗ not found": "✗ not found" in text,
        "cost line present": "$0.00" in text,
        "skipped merges reported": "skipped as merge artifacts" in text,
        "JSON written alongside": path.with_suffix(".json").exists(),
    }
    for label, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {label}")
    return all(checks.values())


def test_cache_key_compatible_with_v1():
    """
    Added and modified changes must keep the exact v1 cache key, or the first
    full run's 54 cached answers would be thrown away and paid for again.
    """
    import hashlib
    change = {"kind": "modified", "old": OLD_MOD, "new": NEW_MOD}
    v1 = hashlib.sha256(json.dumps(
        ["v1", "claude-haiku-4-5-20251001", "modified", OLD_MOD, NEW_MOD],
        ensure_ascii=False).encode()).hexdigest()[:24]
    same = summarise.cache_key("claude-haiku-4-5-20251001", change) == v1

    removed_a = {"kind": "removed", "old": OLD, "new": None,
                 "candidates": [{"text": "one", "containment": 0.4}]}
    removed_b = {**removed_a, "candidates": [{"text": "two", "containment": 0.4}]}
    differs = (summarise.cache_key("m", removed_a) != summarise.cache_key("m", removed_b))

    print("\n=== cache compatibility ===")
    print(f"  {'PASS' if same else 'FAIL'}  modified/added keys identical to v1 (cached answers reused)")
    print(f"  {'PASS' if differs else 'FAIL'}  removal key changes when its candidates change")
    return same and differs


# Single-source supplier paragraph (#6 in the hand verification): the diff
# called it removed, but FY2025 still discloses it in a longer paragraph.
SUPPLIER_OLD = ("The Company relies on single-source outsourcing partners in the U.S., Asia and "
                "Europe to supply and manufacture many components, and on outsourcing partners "
                "primarily located in Asia, for final assembly of substantially all of the "
                "Company’s hardware products.")
SUPPLIER_HOST = ("A significant majority of the Company’s manufacturing is performed in whole or "
                 "in part by outsourcing partners located primarily in China mainland, India, Japan, "
                 "South Korea, Taiwan and Vietnam. The Company relies on single-source partners in "
                 "the U.S., Asia and Europe to supply and manufacture many components, and on "
                 "partners primarily located in Asia, for final assembly of substantially all of "
                 "the Company’s hardware products.")


def removed_answer(verdict, evidence, materiality="low"):
    return {"evidence": evidence, "verdict": verdict, "summary": "s",
            "materiality": materiality, "materiality_reason": "r"}


def test_removal_judgment(tmp: Path):
    summarise.CACHE_DIR = tmp / "cache_removed"
    change = {"kind": "removed", "old": SUPPLIER_OLD, "new": None,
              "candidates": [{"text": SUPPLIER_HOST, "containment": 0.37}]}

    sent = {}

    class Recorder(FakeClient):
        def create(self, **kwargs):
            sent.update(kwargs)
            return super().create(**kwargs)

    good = removed_answer("moved_or_reworded", [
        {"source": "old", "quote": "The Company relies on single-source outsourcing partners"},
        {"source": "new", "quote": "The Company relies on single-source partners in the U.S., Asia and Europe"},
    ])
    row = summarise_change(Recorder([good]), "claude-haiku-4-5-20251001", change)
    message = sent["messages"][0]["content"]
    schema = sent["output_config"]["format"]["schema"]

    print("\n=== removals are judged, not trusted ===")
    checks = {
        "removal prompt and schema used (verdict field required)":
            "verdict" in schema["required"] and sent["system"] == summarise.REMOVED_PROMPT,
        "candidate paragraph is shown to the model":
            "CANDIDATE 1" in message and "single-source partners in the U.S." in message,
        "\"new\" quote is checked against the candidate text":
            row["check"]["evidence"][1]["found"] and row["check"]["status"] == "VERIFIED",
        "\"moved\" verdict supported by a found new-filing quote":
            row["check"]["verdict_supported"] is True,
    }

    no_proof = check_evidence(change, [{"source": "old", "quote": "The Company relies on single-source outsourcing partners"}],
                              verdict="moved_or_reworded")
    checks["\"moved\" verdict with no new-filing quote is flagged"] = no_proof["verdict_supported"] is False

    invented = check_evidence(change, [{"source": "new", "quote": "Apple still relies on suppliers in Asia"}],
                              verdict="moved_or_reworded")
    checks["\"moved\" verdict citing an invented new quote is flagged"] = invented["verdict_supported"] is False

    removed_ok = check_evidence(change, [{"source": "old", "quote": "The Company relies on single-source outsourcing partners"}],
                                verdict="removed")
    checks["\"removed\" verdict needs no new-filing quote"] = removed_ok["verdict_supported"] is True

    for label, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {label}")
    return all(checks.values())


def test_candidates_attached():
    import test_verify as tv
    changes, _ = collect_changes(tv.OLD, tv.NEW)
    removed = [c for c in changes if c["kind"] == "removed"]
    others = [c for c in changes if c["kind"] != "removed"]
    cands = removed[0].get("candidates")

    print("\n=== candidates ===")
    ok = (cands is not None and 0 < len(cands) <= summarise.N_CANDIDATES
          and all("text" in c and "containment" in c for c in cands)
          and all("candidates" not in c for c in others))
    print(f"  {'PASS' if ok else 'FAIL'}  each removal carries up to "
          f"{summarise.N_CANDIDATES} surviving candidates; other changes carry none")
    return ok


def test_hand_labels_and_scoring(tmp: Path):
    """Parses verify.py's review file and scores verdicts against it."""
    review = tmp / "review.txt"
    review.write_text(
        "header\n\n"
        "--- 1. LIKELY REAL REMOVAL  (containment=0.367) ---\n"
        f"REMOVED (783 chars):\n  {SUPPLIER_OLD}\n\n"
        "CLOSEST TEXT IN NEW FILING:\n  whatever\n\n"
        "  your verdict: REWORDED\n\n"
        "--- 2. LIKELY REAL REMOVAL  (containment=0.294) ---\n"
        f"REMOVED (609 chars):\n  {OLD}\n\n"
        "  your verdict: REAL\n\n"
        "--- 3. LIKELY REAL REMOVAL  (containment=0.313) ---\n"
        "REMOVED (50 chars):\n  Some seasonal paragraph text here for the test.\n\n"
        "  your verdict: REWORDED PARTIAL\n\n"
        "--- 4. LIKELY REAL REMOVAL ---\n"
        "REMOVED (40 chars):\n  An entry nobody reviewed yet, left blank.\n\n"
        "  your verdict: ______________________\n"
    )
    labels = summarise.load_hand_labels(review)

    rows = [
        {"kind": "removed", "old": SUPPLIER_OLD, "verdict": "moved_or_reworded"},
        {"kind": "removed", "old": OLD, "verdict": "moved_or_reworded"},
    ]
    score = summarise.score_removals(rows, labels)

    print("\n=== hand-label scoring ===")
    checks = {
        "REWORDED -> moved_or_reworded": labels.get(summarise.removal_key(SUPPLIER_OLD)) == "moved_or_reworded",
        "REAL -> removed": labels.get(summarise.removal_key(OLD)) == "removed",
        "REWORDED PARTIAL -> partially_removed (PARTIAL wins)":
            "partially_removed" in labels.values(),
        "blank verdict ignored": len(labels) == 3,
        "model agreement 1/2, diff-label baseline 1/2":
            score and (score["model_agree"], score["diff_agree"], score["n"]) == (1, 1, 2),
    }
    for label, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {label}")
    return all(checks.values())


def test_digest_removal_section(tmp: Path):
    summarise.RESULTS_DIR = tmp / "results_removal"
    change = {"kind": "removed", "old": SUPPLIER_OLD, "new": None,
              "candidates": [{"text": SUPPLIER_HOST, "containment": 0.37}]}
    ev = [{"source": "old", "quote": "The Company relies on single-source outsourcing partners"}]
    row = {**change, **removed_answer("moved_or_reworded", ev),
           "check": check_evidence(change, ev, "moved_or_reworded"),
           "input_tokens": 600, "output_tokens": 100, "cached": False}
    labels = {summarise.removal_key(SUPPLIER_OLD): "moved_or_reworded"}
    text = write_digest("AAPL", "1A", "claude-haiku-4-5-20251001", [row],
                        skipped=["a", "b", "c"], labels=labels).read_text()

    print("\n=== digest: removals ===")
    checks = {
        "verdict shown instead of a bare REMOVED": "NOT REMOVED (moved or reworded)" in text,
        "removal tally (flagged / skipped / judged)": "flagged 4 paragraphs as removed" in text,
        "agreement with hand verification reported": "matched 1 of 1" in text,
        "unproven \"moved\" verdict flagged": "VERDICT UNSUPPORTED" in text,
    }
    for label, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {label}")
    return all(checks.values())


if __name__ == "__main__":
    tmp = Path(tempfile.mkdtemp())
    try:
        results = [test_grounding(), test_cache_and_cost(tmp),
                   test_merge_artifacts_skipped(), test_digest(tmp),
                   test_cache_key_compatible_with_v1(), test_removal_judgment(tmp),
                   test_candidates_attached(), test_hand_labels_and_scoring(tmp),
                   test_digest_removal_section(tmp)]
    finally:
        shutil.rmtree(tmp)
    print(f"\n{sum(results)}/{len(results)} checks passed")
