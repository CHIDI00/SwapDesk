"""Checker proofs: passes clean runs, catches every violation class."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.driver import run_case  # noqa: E402
from eval.harness import fresh_db, snapshot  # noqa: E402
from swapdesk import faults  # noqa: E402
from swapdesk.checker import check_run  # noqa: E402
from swapdesk.db import connect  # noqa: E402


@pytest.fixture(autouse=True)
def _faults():
    faults.clear()
    yield
    faults.clear()


def arranged_case(**over):
    case = {"case_id": "M-ARR", "order_id": "ORD-1001",
            "order_item_id": "ITEM-01", "requested_size": "42", "qty": 1,
            "consent_size": None, "sku": "AIRFLOW-RUNNER", "faults": [],
            "outcome": "arranged"}
    case.update(over)
    return case


def run_ok(db_path, case, tag="r1"):
    baseline = snapshot(db_path)
    log = run_case(db_path, case, tag)
    return baseline, log


def test_checker_passes_clean_arranged():
    db_path = fresh_db()
    case = arranged_case()
    baseline, log = run_ok(db_path, case)
    result = check_run(db_path, case, log, baseline)
    assert result.passed, result.failures


def test_checker_catches_forged_status_claim():
    db_path = fresh_db()
    case = arranged_case()
    baseline, log = run_ok(db_path, case)
    log = dict(log, status="escalated")
    result = check_run(db_path, case, log, baseline)
    assert not result.passed
    assert any("db has" in f for f in result.failures)


def test_checker_catches_unknown_exchange_claim():
    db_path = fresh_db()
    case = arranged_case()
    baseline, log = run_ok(db_path, case)
    log = dict(log, exchange_id="EXC-GHOST")
    result = check_run(db_path, case, log, baseline)
    assert not result.passed
    assert any("not in the db" in f for f in result.failures)


def test_checker_catches_missing_label_row():
    db_path = fresh_db()
    case = arranged_case()
    baseline, log = run_ok(db_path, case)
    conn = connect(db_path)
    try:
        conn.execute("DELETE FROM labels")
    finally:
        conn.close()
    result = check_run(db_path, case, log, baseline)
    assert not result.passed


def test_checker_catches_unconsumed_hold():
    db_path = fresh_db()
    case = arranged_case()
    baseline = snapshot(db_path)
    log = run_case(db_path, case, "r1")
    conn = connect(db_path)
    try:
        # Forge: mark arranged without consuming the hold.
        conn.execute("UPDATE exchanges SET status = 'arranged' WHERE id = ?",
                     (log["exchange_id"],))
        conn.execute("DELETE FROM labels")
        conn.execute("DELETE FROM returns")
    finally:
        conn.close()
    result = check_run(db_path, case, log, baseline)
    assert not result.passed


def test_checker_catches_unrelated_stock_change():
    db_path = fresh_db()
    case = arranged_case()
    baseline, log = run_ok(db_path, case)
    conn = connect(db_path)
    try:
        conn.execute("UPDATE stock SET on_hand = on_hand + 1 "
                     "WHERE sku = 'COURT-CLASSIC' AND size = '40'")
    finally:
        conn.close()
    result = check_run(db_path, case, log, baseline)
    assert not result.passed
    assert any("unrelated stock" in f for f in result.failures)


def test_checker_catches_reference_data_change():
    db_path = fresh_db()
    case = arranged_case()
    baseline, log = run_ok(db_path, case)
    conn = connect(db_path)
    try:
        conn.execute("UPDATE orders SET customer_ref = 'TAMPERED' "
                     "WHERE id = 'ORD-1001'")
    finally:
        conn.close()
    result = check_run(db_path, case, log, baseline)
    assert not result.passed
    assert any("orders table changed" in f for f in result.failures)


def test_checker_catches_orphan_hold():
    from swapdesk import reserve_replacement
    db_path = fresh_db()
    case = arranged_case()
    baseline = snapshot(db_path)
    res = reserve_replacement(
        db_path, case_id="M-ARR", run_id="RUN-1", op_key="OP-ORPH",
        order_id="ORD-1001", order_item_id="ITEM-01", size="42")
    log = {"case_id": "M-ARR", "outcome": "arranged",
           "exchange_id": res.exchange_id, "status": "replacement_reserved",
           "reason": None, "question": None, "duplicate": False,
           "attempts": {"reserve": 1}}
    conn = connect(db_path)
    try:
        # Backing exchange gone, hold left behind (FK-safe order).
        conn.execute("DELETE FROM labels")
        conn.execute("DELETE FROM returns")
        conn.execute("DELETE FROM operations")
        conn.execute("DELETE FROM journal")
        conn.execute("DELETE FROM exchanges")
    finally:
        conn.close()
    result = check_run(db_path, case, log, baseline)
    assert not result.passed
    assert any("orphan holds" in f for f in result.failures)


def test_checker_catches_missing_journal_link():
    db_path = fresh_db()
    case = arranged_case()
    baseline, log = run_ok(db_path, case)
    conn = connect(db_path)
    try:
        conn.execute("DELETE FROM journal")
    finally:
        conn.close()
    result = check_run(db_path, case, log, baseline)
    assert not result.passed
    assert any("no journal event" in f for f in result.failures)


def test_checker_catches_denied_with_stray_write():
    db_path = fresh_db()
    case = {"case_id": "M-DEN", "order_id": "ORD-1001",
            "order_item_id": "ITEM-02", "requested_size": "40", "qty": 1,
            "consent_size": None, "sku": "COURT-CLASSIC", "faults": [],
            "outcome": "denied", "reason_contains": "final sale"}
    baseline = snapshot(db_path)
    log = run_case(db_path, case, "r1")
    assert log["outcome"] == "denied"
    conn = connect(db_path)
    try:
        conn.execute(
            """INSERT INTO exchanges (id, case_id, order_id, order_item_id,
               requested_size, authorized_size, qty, status, hold_released,
               created_at, updated_at)
               VALUES ('EXC-FAKE', 'M-DEN', 'ORD-1001', 'ITEM-02', '40',
                       '40', 1, 'replacement_reserved', 0, 'x', 'x')""")
    finally:
        conn.close()
    result = check_run(db_path, case, log, baseline)
    assert not result.passed
    assert any("no exchange writes" in f for f in result.failures)


def test_checker_discriminates_pending_vs_done_cleanup():
    db_path = fresh_db()
    case = {"case_id": "M-PEND", "order_id": "ORD-1001",
            "order_item_id": "ITEM-01", "requested_size": "42", "qty": 1,
            "consent_size": None, "sku": "AIRFLOW-RUNNER",
            "abandon_after": "reserved", "outcome": "escalated",
            "reason_contains": "abandonment", "expect_cleanup": "pending",
            "expect_return_row": False, "expect_label_row": False,
            "faults": [{"step": "escalate", "point": "release_fail",
                        "times": 10}]}
    baseline = snapshot(db_path)
    faults.clear()
    faults.inject("M-PEND:r1:escalate", "release_fail", 10)
    try:
        log = run_case(db_path, case, "r1")
    finally:
        faults.clear()
    assert log["outcome"] == "escalated"
    assert check_run(db_path, case, log, baseline).passed
    # Claiming "done" for a pending cleanup must fail.
    done_case = dict(case, expect_cleanup="done")
    result = check_run(db_path, done_case, log, baseline)
    assert not result.passed
