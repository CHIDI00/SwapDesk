"""Slice 2 proofs: the complete mock exchange holds under failures."""

import pytest

from swapdesk import (
    IllegalTransitionError,
    InsufficientStockError,
    LabelTimeoutError,
    OperationError,
    PayloadMismatchError,
    ReleaseFailedError,
    ReservationError,
    TransientError,
    WorkerCrashedError,
    cancel_exchange,
    create_label,
    create_return,
    escalate_case,
    faults,
    finalize_arranged,
    get_case,
    get_operation_status,
    note_case,
    record_escalation,
    release_reservation,
    reserve_replacement,
    verify_exchange,
)
from swapdesk.db import connect, init_db
from swapdesk.fixtures import load_fixtures


@pytest.fixture()
def shop(tmp_path):
    db_path = tmp_path / "shop.db"
    conn = connect(db_path)
    init_db(conn)
    load_fixtures(conn)
    conn.close()
    return db_path


@pytest.fixture(autouse=True)
def _faults():
    faults.clear()
    yield
    faults.clear()


def stock_snapshot(db_path):
    conn = connect(db_path)
    try:
        return {(r["sku"], r["size"]): (r["on_hand"], r["held"])
                for r in conn.execute("SELECT * FROM stock")}
    finally:
        conn.close()


def table_count(db_path, table):
    conn = connect(db_path)
    try:
        return conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
    finally:
        conn.close()


def reserve_item01(db_path, case="CASE-10", run="RUN-10", key="OP-R"):
    return reserve_replacement(
        db_path, case_id=case, run_id=run, op_key=key,
        order_id="ORD-1001", order_item_id="ITEM-01", size="42")


def test_full_exchange_arranges(shop):
    note_case(shop, case_id="CASE-10", state="received")
    res = reserve_item01(shop)
    ret = create_return(shop, case_id="CASE-10", run_id="RUN-10",
                        op_key="OP-RET", exchange_id=res.exchange_id)
    lab = create_label(shop, case_id="CASE-10", run_id="RUN-10",
                       op_key="OP-LBL", exchange_id=res.exchange_id)
    fin = finalize_arranged(shop, case_id="CASE-10", run_id="RUN-10",
                            op_key="OP-FIN", exchange_id=res.exchange_id)
    assert fin.status == "arranged"
    assert fin.duplicate is False
    handoff = verify_exchange(shop, res.exchange_id)
    assert handoff.status == "arranged"
    assert handoff.return_id == ret.return_id
    assert handoff.label_id == lab.label_id
    assert handoff.tracking_ref == lab.tracking_ref
    assert handoff.hold_active is False
    assert handoff.pending_cleanup is False
    assert handoff.consistent is True
    assert handoff.suggested_next == "none"
    # The hold was consumed into a mock shipment: no orphan hold remains.
    assert stock_snapshot(shop)[("AIRFLOW-RUNNER", "42")] == (9, 0)
    case = get_case(shop, "CASE-10")
    assert case["state"] == "arranged"
    for step in ("reserved", "returned", "labeled", "arranged"):
        assert step in case["progress"]["steps"]


def test_return_label_idempotent_replay(shop):
    res = reserve_item01(shop)
    first_ret = create_return(shop, case_id="CASE-10", run_id="RUN-10",
                              op_key="OP-RET", exchange_id=res.exchange_id)
    again_ret = create_return(shop, case_id="CASE-10", run_id="RUN-10",
                              op_key="OP-RET", exchange_id=res.exchange_id)
    assert again_ret.return_id == first_ret.return_id
    assert again_ret.duplicate is True
    first_lab = create_label(shop, case_id="CASE-10", run_id="RUN-10",
                             op_key="OP-LBL", exchange_id=res.exchange_id)
    again_lab = create_label(shop, case_id="CASE-10", run_id="RUN-10",
                             op_key="OP-LBL", exchange_id=res.exchange_id)
    assert again_lab.label_id == first_lab.label_id
    assert table_count(shop, "returns") == 1
    assert table_count(shop, "labels") == 1


def test_fresh_key_after_committed_step_is_rejected(shop):
    res = reserve_item01(shop)
    create_return(shop, case_id="CASE-10", run_id="RUN-10",
                  op_key="OP-RET", exchange_id=res.exchange_id)
    with pytest.raises(IllegalTransitionError):
        create_return(shop, case_id="CASE-10", run_id="RUN-10",
                      op_key="OP-OTHER", exchange_id=res.exchange_id)
    with pytest.raises(PayloadMismatchError):
        create_return(shop, case_id="CASE-10", run_id="RUN-10",
                      op_key="OP-RET", exchange_id="EXC-NOPE")
    assert table_count(shop, "returns") == 1


def test_illegal_transition_writes_nothing(shop):
    res = reserve_item01(shop)
    with pytest.raises(IllegalTransitionError):
        create_label(shop, case_id="CASE-10", run_id="RUN-10",
                     op_key="OP-LBL", exchange_id=res.exchange_id)
    with pytest.raises(IllegalTransitionError):
        finalize_arranged(shop, case_id="CASE-10", run_id="RUN-10",
                          op_key="OP-FIN", exchange_id=res.exchange_id)
    assert table_count(shop, "labels") == 0
    handoff = verify_exchange(shop, res.exchange_id)
    assert handoff.status == "replacement_reserved"
    assert handoff.suggested_next == "create_return"
    assert stock_snapshot(shop)[("AIRFLOW-RUNNER", "42")] == (10, 1)


def test_label_timeout_commits_then_recovers(shop):
    res = reserve_item01(shop)
    create_return(shop, case_id="CASE-10", run_id="RUN-10",
                  op_key="OP-RET", exchange_id=res.exchange_id)
    faults.inject("OP-LBL", "timeout")
    with pytest.raises(LabelTimeoutError):
        create_label(shop, case_id="CASE-10", run_id="RUN-10",
                     op_key="OP-LBL", exchange_id=res.exchange_id)
    # The response was lost, not the effect: the op is committed.
    status = get_operation_status(shop, "OP-LBL")
    assert status["status"] == "committed"
    retry = create_label(shop, case_id="CASE-10", run_id="RUN-10",
                         op_key="OP-LBL", exchange_id=res.exchange_id)
    assert retry.label_id == status["result"]["label_id"]
    assert retry.duplicate is True
    assert table_count(shop, "labels") == 1
    assert verify_exchange(shop, res.exchange_id).status == "label_created"


def test_stock_vanish_between_lookup_and_reserve(shop):
    before = stock_snapshot(shop)
    faults.inject("OP-R", "deplete_stock")
    with pytest.raises(InsufficientStockError):
        reserve_item01(shop)
    assert stock_snapshot(shop) == before
    assert table_count(shop, "exchanges") == 0
    assert table_count(shop, "operations") == 0


def test_crash_after_reserve_recovers_via_status(shop):
    faults.inject("OP-R3", "crash")
    with pytest.raises(WorkerCrashedError):
        reserve_replacement(
            shop, case_id="CASE-11", run_id="RUN-11", op_key="OP-R3",
            order_id="ORD-1002", order_item_id="ITEM-03", size="42")
    status = get_operation_status(shop, "OP-R3")
    assert status["status"] == "committed"
    assert stock_snapshot(shop)[("TRAIL-BEAST", "42")] == (1, 1)
    handoff = verify_exchange(shop, status["result"]["exchange_id"])
    assert handoff.status == "replacement_reserved"
    assert handoff.hold_active is True
    assert handoff.consistent is True
    assert handoff.suggested_next == "create_return"
    retry = reserve_replacement(
        shop, case_id="CASE-11", run_id="RUN-11", op_key="OP-R3",
        order_id="ORD-1002", order_item_id="ITEM-03", size="42")
    assert retry.exchange_id == status["result"]["exchange_id"]
    assert stock_snapshot(shop)[("TRAIL-BEAST", "42")] == (1, 1)


def test_transient_then_success_and_exhaustion(shop):
    faults.inject("OP-RT", "transient", times=2)
    with pytest.raises(TransientError):
        reserve_item01(shop, case="CASE-12", run="RUN-12", key="OP-RT")
    with pytest.raises(TransientError):
        reserve_item01(shop, case="CASE-12", run="RUN-12", key="OP-RT")
    ok = reserve_item01(shop, case="CASE-12", run="RUN-12", key="OP-RT")
    assert ok.duplicate is False
    assert table_count(shop, "exchanges") == 1

    faults.inject("OP-NEVER", "transient", times=10)
    for _ in range(3):
        with pytest.raises(TransientError):
            reserve_replacement(
                shop, case_id="CASE-13", run_id="RUN-13", op_key="OP-NEVER",
                order_id="ORD-1003", order_item_id="ITEM-04", size="44")
    assert table_count(shop, "operations") == 1  # only OP-RT committed


def test_cleanup_failure_stays_pending_then_escalates(shop):
    res = reserve_item01(shop)
    faults.inject("OP-REL", "release_fail")
    with pytest.raises(ReleaseFailedError):
        release_reservation(shop, case_id="CASE-10", run_id="RUN-10",
                            op_key="OP-REL", exchange_id=res.exchange_id,
                            reason="carrier refused mock pickup")
    handoff = verify_exchange(shop, res.exchange_id)
    assert handoff.status == "cleanup_pending"
    assert handoff.pending_cleanup is True
    assert handoff.hold_active is True
    assert handoff.suggested_next == "release_reservation"
    assert get_operation_status(shop, "OP-REL")["status"] == "failed"
    assert stock_snapshot(shop)[("AIRFLOW-RUNNER", "42")] == (10, 1)
    done = release_reservation(shop, case_id="CASE-10", run_id="RUN-10",
                               op_key="OP-REL", exchange_id=res.exchange_id,
                               reason="carrier refused mock pickup")
    assert done.status == "escalated"
    assert done.hold_released is True
    assert stock_snapshot(shop)[("AIRFLOW-RUNNER", "42")] == (10, 0)
    assert get_operation_status(shop, "OP-REL")["status"] == "committed"


def test_escalation_releases_hold_idempotently(shop):
    res = reserve_item01(shop)
    out = escalate_case(shop, case_id="CASE-10", run_id="RUN-10",
                        op_key="OP-ESC", exchange_id=res.exchange_id,
                        reason="customer asked for a human")
    assert out.status == "escalated"
    assert out.hold_released is True
    held = stock_snapshot(shop)[("AIRFLOW-RUNNER", "42")]
    assert held == (10, 0)
    again = release_reservation(shop, case_id="CASE-10", run_id="RUN-10",
                                op_key="OP-REL2", exchange_id=res.exchange_id)
    assert again.duplicate is True
    assert stock_snapshot(shop)[("AIRFLOW-RUNNER", "42")] == held
    handoff = verify_exchange(shop, res.exchange_id)
    assert handoff.consistent is True
    assert handoff.hold_active is False
    assert handoff.suggested_next == "none"


def test_cancel_then_new_attempt_creates_fresh_exchange(shop):
    first = reserve_item01(shop)
    out = cancel_exchange(shop, case_id="CASE-10", run_id="RUN-10",
                          op_key="OP-CXL", exchange_id=first.exchange_id,
                          reason="customer changed mind")
    assert out.status == "cancelled"
    assert stock_snapshot(shop)[("AIRFLOW-RUNNER", "42")] == (10, 0)
    second = reserve_item01(shop, case="CASE-14", run="RUN-14", key="OP-R2")
    assert second.duplicate is False
    assert second.exchange_id != first.exchange_id
    assert stock_snapshot(shop)[("AIRFLOW-RUNNER", "42")] == (10, 1)


def test_duplicate_after_arranged_returns_existing(shop):
    res = reserve_item01(shop)
    create_return(shop, case_id="CASE-10", run_id="RUN-10",
                  op_key="OP-RET", exchange_id=res.exchange_id)
    create_label(shop, case_id="CASE-10", run_id="RUN-10",
                 op_key="OP-LBL", exchange_id=res.exchange_id)
    finalize_arranged(shop, case_id="CASE-10", run_id="RUN-10",
                      op_key="OP-FIN", exchange_id=res.exchange_id)
    before = stock_snapshot(shop)
    dup = reserve_item01(shop, case="CASE-15", run="RUN-15", key="OP-RD")
    assert dup.duplicate is True
    assert dup.exchange_id == res.exchange_id
    assert dup.status == "arranged"
    assert stock_snapshot(shop) == before
    assert table_count(shop, "exchanges") == 1


def test_case_notes_have_no_fulfillment_effect(shop):
    note_case(shop, case_id="CASE-20", state="received")
    note_case(shop, case_id="CASE-20", state="needs_information",
              detail="need order number")
    note_case(shop, case_id="CASE-20", state="denied",
              detail="final sale")
    assert get_case(shop, "CASE-20")["state"] == "denied"
    assert table_count(shop, "exchanges") == 0
    assert table_count(shop, "operations") == 0
    with pytest.raises(OperationError):
        note_case(shop, case_id="CASE-20", state="bogus-state")


def test_blank_terminal_notes_are_rejected(shop):
    with pytest.raises(OperationError):
        note_case(shop, case_id='CASE-30', state='denied', detail='   ')
    with pytest.raises(OperationError):
        note_case(shop, case_id='CASE-30', state='needs_information')
    with pytest.raises(OperationError):
        record_escalation(shop, case_id='CASE-30', run_id='RUN-30', op_key='OP-E', reason='')
    assert get_case(shop, 'CASE-30') is None


def test_unconsented_substitution_is_rejected(shop):
    before = stock_snapshot(shop)
    with pytest.raises(ReservationError):
        reserve_replacement(shop, case_id='CASE-31', run_id='RUN-31', op_key='OP-S', order_id='ORD-1005', order_item_id='ITEM-06', size='42', requested_size='43')
    assert stock_snapshot(shop) == before
    ok = reserve_replacement(shop, case_id='CASE-31', run_id='RUN-31', op_key='OP-S2', order_id='ORD-1005', order_item_id='ITEM-06', size='42', requested_size='43', consent=True)
    assert ok.status == 'replacement_reserved'


def test_escalation_without_exchange_is_journaled(shop):
    first = record_escalation(shop, case_id='CASE-32', run_id='RUN-32', op_key='OP-X', reason='repeated stock failures')
    assert first.status == 'escalated' and first.duplicate is False
    second = record_escalation(shop, case_id='CASE-32', run_id='RUN-32', op_key='OP-X', reason='repeated stock failures')
    assert second.duplicate is True
    status = get_operation_status(shop, 'OP-X')
    assert status['status'] == 'committed'
    assert get_case(shop, 'CASE-32')['state'] == 'escalated'

