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
        "skipped merges reported": "skipped as likely merge artifacts" in text,
        "JSON written alongside": path.with_suffix(".json").exists(),
    }
    for label, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {label}")
    return all(checks.values())


if __name__ == "__main__":
    tmp = Path(tempfile.mkdtemp())
    try:
        results = [test_grounding(), test_cache_and_cost(tmp),
                   test_merge_artifacts_skipped(), test_digest(tmp)]
    finally:
        shutil.rmtree(tmp)
    print(f"\n{sum(results)}/{len(results)} checks passed")
