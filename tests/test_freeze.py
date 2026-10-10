"""Frozen benchmark guards: case file validity plus a full 42-run pass."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.harness import run_benchmark  # noqa: E402

CASES_PATH = Path(__file__).resolve().parent.parent / "eval" / "cases_v1.json"

VALID_STEPS = {"reserve", "return", "label", "finalize", "escalate"}
VALID_POINTS = {"transient", "deplete_stock", "crash", "timeout",
                "release_fail"}
VALID_SCRIPTS = {"standard", "rerun", "cross_case", "cancel_fresh"}


def load_cases():
    doc = json.loads(CASES_PATH.read_text())
    assert doc.get("version") == "benchmark-v1"
    return doc["cases"]


def test_frozen_case_file_is_valid():
    cases = load_cases()
    assert len(cases) == 30
    ids = [c["case_id"] for c in cases]
    assert len(set(ids)) == 30
    assert sum(1 for c in cases if c.get("holdout")) == 8
    assert sum(c.get("repeats", 1) for c in cases) == 42
    for case in cases:
        for field in ("order_id", "order_item_id", "requested_size", "sku",
                      "outcome"):
            assert field in case, f"{case['case_id']} misses {field}"
        assert case["outcome"] in ("arranged", "denied", "clarification",
                                   "escalated")
        assert case.get("script", "standard") in VALID_SCRIPTS
        for fault in case.get("faults", []):
            assert fault["step"] in VALID_STEPS, case["case_id"]
            assert fault["point"] in VALID_POINTS, case["case_id"]
            assert fault.get("times", 1) >= 1
        if case["outcome"] == "arranged" and case.get("consent_size"):
            assert case["requested_size"] != case["consent_size"]
    by_outcome = {}
    for case in cases:
        by_outcome[case["outcome"]] = by_outcome.get(case["outcome"], 0) + 1
    assert by_outcome == {"arranged": 15, "denied": 4, "clarification": 5,
                          "escalated": 6}


def test_full_benchmark_passes(tmp_path):
    cases = load_cases()
    results = run_benchmark(cases)
    assert results["total"] == 42
    failures = [r for r in results["runs"] if not r["passed"]]
    assert not failures, failures[:3]
    assert results["passed"] == 42
    out = tmp_path / "results.json"
    out.write_text(json.dumps(results, indent=2, sort_keys=True))
    assert out.stat().st_size > 0
