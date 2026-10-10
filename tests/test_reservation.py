"""Slice 1 proofs: the reservation foundation holds under every case."""

import sqlite3
import threading

import pytest

from swapdesk import (
    IneligibleError,
    InsufficientStockError,
    PayloadMismatchError,
    get_operation_status,
    reserve_replacement,
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


def stock_snapshot(db_path):
    conn = connect(db_path)
    try:
        return {(r["sku"], r["size"]): (r["on_hand"], r["held"])
                for r in conn.execute("SELECT * FROM stock")}
    finally:
        conn.close()


def test_eligible_reservation_succeeds(shop):
    before = stock_snapshot(shop)
    result = reserve_replacement(
        shop, case_id="CASE-01", run_id="RUN-01", op_key="OP-01",
        order_id="ORD-1001", order_item_id="ITEM-01", size="42")
    assert result.status == "replacement_reserved"
    assert result.duplicate is False
    after = stock_snapshot(shop)
    assert after[("AIRFLOW-RUNNER", "42")] == (
        before[("AIRFLOW-RUNNER", "42")][0],
        before[("AIRFLOW-RUNNER", "42")][1] + 1)
    status = get_operation_status(shop, "OP-01")
    assert status["status"] == "committed"
    assert status["result"]["exchange_id"] == result.exchange_id


def test_same_key_same_payload_does_not_reserve_twice(shop):
    first = reserve_replacement(
        shop, case_id="CASE-01", run_id="RUN-01", op_key="OP-01",
        order_id="ORD-1001", order_item_id="ITEM-01", size="42")
    held_after_first = stock_snapshot(shop)[("AIRFLOW-RUNNER", "42")][1]
    second = reserve_replacement(
        shop, case_id="CASE-01", run_id="RUN-01", op_key="OP-01",
        order_id="ORD-1001", order_item_id="ITEM-01", size="42")
    assert second.exchange_id == first.exchange_id
    assert stock_snapshot(shop)[("AIRFLOW-RUNNER", "42")][1] == held_after_first


def test_same_key_different_payload_is_rejected(shop):
    reserve_replacement(
        shop, case_id="CASE-01", run_id="RUN-01", op_key="OP-01",
        order_id="ORD-1001", order_item_id="ITEM-01", size="42")
    with pytest.raises(PayloadMismatchError):
        reserve_replacement(
            shop, case_id="CASE-01", run_id="RUN-01", op_key="OP-01",
            order_id="ORD-1001", order_item_id="ITEM-01", size="43")


def test_ineligible_request_leaves_inventory_unchanged(shop):
    before = stock_snapshot(shop)
    with pytest.raises(IneligibleError):
        reserve_replacement(
            shop, case_id="CASE-02", run_id="RUN-02", op_key="OP-02",
            order_id="ORD-1001", order_item_id="ITEM-02", size="40")
    with pytest.raises(IneligibleError):
        reserve_replacement(
            shop, case_id="CASE-03", run_id="RUN-03", op_key="OP-03",
            order_id="ORD-1004", order_item_id="ITEM-05", size="43")
    assert stock_snapshot(shop) == before
    conn = connect(shop)
    try:
        assert conn.execute("SELECT COUNT(*) AS n FROM exchanges").fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM operations").fetchone()["n"] == 0
    finally:
        conn.close()


def test_insufficient_stock_leaves_inventory_unchanged(shop):
    before = stock_snapshot(shop)
    with pytest.raises(InsufficientStockError):
        reserve_replacement(
            shop, case_id="CASE-04", run_id="RUN-04", op_key="OP-04",
            order_id="ORD-1005", order_item_id="ITEM-06", size="43")
    assert stock_snapshot(shop) == before


def test_distinct_cases_cannot_double_exchange_one_item(shop):
    first = reserve_replacement(
        shop, case_id="CASE-A", run_id="RUN-A", op_key="OP-A",
        order_id="ORD-1002", order_item_id="ITEM-03", size="42")
    held = stock_snapshot(shop)[("TRAIL-BEAST", "42")][1]
    second = reserve_replacement(
        shop, case_id="CASE-B", run_id="RUN-B", op_key="OP-B",
        order_id="ORD-1002", order_item_id="ITEM-03", size="42")
    assert second.duplicate is True
    assert second.exchange_id == first.exchange_id
    assert stock_snapshot(shop)[("TRAIL-BEAST", "42")][1] == held


def test_concurrent_reservations_cannot_oversell(shop):
    # COURT-CLASSIC 44 has exactly 2 units shared by ITEM-04 and ITEM-07.
    outcomes, errors = [], []
    items = ["ITEM-04", "ITEM-07", "ITEM-04", "ITEM-07", "ITEM-04"]

    def attempt(n):
        try:
            outcomes.append(reserve_replacement(
                shop, case_id=f"CASE-C{n}", run_id=f"RUN-C{n}",
                op_key=f"OP-C{n}", order_id="ORD-1003",
                order_item_id=items[n], size="44"))
        except Exception as exc:  # noqa: BLE001 - collected below
            errors.append(exc)

    threads = [threading.Thread(target=attempt, args=(n,)) for n in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    committed = [o for o in outcomes if not o.duplicate]
    duplicates = [o for o in outcomes if o.duplicate]
    assert len(committed) == 2
    assert len(duplicates) == 3
    assert len({o.exchange_id for o in committed}) == 2
    held = stock_snapshot(shop)[("COURT-CLASSIC", "44")][1]
    assert held == 2


def test_inventory_never_negative_through_history(shop):
    reserve_replacement(
        shop, case_id="CASE-01", run_id="RUN-01", op_key="OP-01",
        order_id="ORD-1001", order_item_id="ITEM-01", size="42")
    conn = connect(shop)
    try:
        rows = conn.execute("SELECT sku, size, on_hand, held FROM stock")
        for row in rows:
            assert row["held"] >= 0
            assert row["on_hand"] - row["held"] >= 0
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM journal WHERE event = 'reserved'"
        ).fetchone()["n"] == 1
    finally:
        conn.close()
