"""Frozen-benchmark harness: fresh DB per run, faults armed, checked.

Each case run gets an isolated database so runs never interfere (except
scripts that intentionally share one DB within a single run). Results
carry case/version identifiers plus the observed outcome; expected
answers stay in the cases file, which the future agent never sees.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from swapdesk import faults
from swapdesk.checker import check_run
from swapdesk.db import connect, init_db
from swapdesk.fixtures import load_fixtures

TABLES = ("orders", "order_items", "stock", "exchanges", "returns",
          "labels", "operations", "journal", "cases")


def fresh_db() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="swapdesk-eval-"))
    db_path = tmp / "shop.db"
    conn = connect(db_path)
    try:
        init_db(conn)
        load_fixtures(conn)
    finally:
        conn.close()
    return db_path


def snapshot(db_path) -> dict:
    conn = connect(db_path)
    try:
        return {t: [dict(r) for r in conn.execute(f"SELECT * FROM {t}")]
                for t in TABLES}
    finally:
        conn.close()


def _arm(case_id: str, run_tag: str, fault_specs: list) -> None:
    for spec in fault_specs:
        faults.inject(f"{case_id}:{run_tag}:{spec['step']}",
                      spec["point"], spec.get("times", 1))


def run_benchmark(cases: list[dict]) -> dict:
    from eval.driver import run_case
    runs = []
    for case in cases:
        for rep in range(1, case.get("repeats", 1) + 1):
            run_tag = f"r{rep}"
            db_path = fresh_db()
            baseline = snapshot(db_path)
            faults.clear()
            _arm(case["case_id"], run_tag, case.get("faults", []))
            second = case.get("second_case")
            if second:
                _arm(second["case_id"], run_tag,
                     second.get("faults", []))
            try:
                log = run_case(db_path, case, run_tag)
            finally:
                faults.clear()
            check = check_run(db_path, case, log, baseline, repeat=rep)
            runs.append({
                "benchmark_version": case.get("_version", "benchmark-v1"),
                "case_id": case["case_id"],
                "repeat": rep,
                "passed": check.passed,
                "failures": check.failures,
                "observed": {
                    "outcome": log.get("outcome"),
                    "exchange_id": log.get("exchange_id"),
                    "status": log.get("status"),
                    "duplicate": log.get("duplicate", False),
                },
            })
    passed = sum(1 for r in runs if r["passed"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "total": len(runs),
        "passed": passed,
        "failed": len(runs) - passed,
        "runs": runs,
    }
