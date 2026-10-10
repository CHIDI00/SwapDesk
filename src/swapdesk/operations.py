"""Validated business operations. The backend enforces every rule here.

reserve_replacement commits atomically in one transaction: the stock hold,
the exchange row, the idempotency record, and the journal event. Reads that
fail validation raise without writing anything.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from . import db as _db
from .models import (
    OP_RESERVE,
    TERMINAL_EXCHANGE_STATUSES,
    ExchangeRecord,
    Order,
    OrderItem,
    ReservationResult,
    StockLevel,
    payload_hash,
)
from .policy import RETURN_WINDOW_DAYS, check_eligibility


class ReservationError(Exception):
    """Base class for failed reservations. Nothing was written."""


class PayloadMismatchError(ReservationError):
    """Same idempotency key was already used with a different payload."""


class IneligibleError(ReservationError):
    """The order item does not qualify for exchange."""


class InsufficientStockError(ReservationError):
    """Not enough available units of the requested size."""


class ItemNotFoundError(ReservationError):
    """Unknown order, item, or item/order mismatch."""


def _row_to_order(row: sqlite3.Row) -> Order:
    return Order(id=row["id"], customer_ref=row["customer_ref"],
                 created_at=row["created_at"])


def _row_to_item(row: sqlite3.Row) -> OrderItem:
    return OrderItem(
        id=row["id"], order_id=row["order_id"], sku=row["sku"],
        size=row["size"], qty=row["qty"], price_cents=row["price_cents"],
        status=row["status"], delivered_at=row["delivered_at"],
        final_sale=bool(row["final_sale"]), created_at=row["created_at"],
    )


def _row_to_stock(row: sqlite3.Row) -> StockLevel:
    return StockLevel(sku=row["sku"], size=row["size"],
                      on_hand=row["on_hand"], held=row["held"])


def _row_to_exchange(row: sqlite3.Row) -> ExchangeRecord:
    return ExchangeRecord(
        id=row["id"], case_id=row["case_id"], order_id=row["order_id"],
        order_item_id=row["order_item_id"],
        requested_size=row["requested_size"],
        authorized_size=row["authorized_size"], qty=row["qty"],
        status=row["status"],
    )


def get_order(conn: sqlite3.Connection, order_id: str) -> Order | None:
    row = conn.execute("SELECT * FROM orders WHERE id = ?",
                       (order_id,)).fetchone()
    return _row_to_order(row) if row else None


def get_return_policy() -> dict:
    return {"window_days": RETURN_WINDOW_DAYS,
            "eligible_status": "delivered",
            "final_sale_excluded": True}


def find_exchange_stock(conn: sqlite3.Connection, sku: str,
                        size: str) -> StockLevel | None:
    row = conn.execute("SELECT * FROM stock WHERE sku = ? AND size = ?",
                       (sku, size)).fetchone()
    return _row_to_stock(row) if row else None


def get_active_exchange(conn: sqlite3.Connection,
                        order_item_id: str) -> ExchangeRecord | None:
    terminal = ",".join(f"'{s}'" for s in TERMINAL_EXCHANGE_STATUSES)
    row = conn.execute(
        f"SELECT * FROM exchanges WHERE order_item_id = ? "
        f"AND status NOT IN ({terminal})",
        (order_item_id,)).fetchone()
    return _row_to_exchange(row) if row else None


def _journal(conn: sqlite3.Connection, op_key: str, event: str,
             details: dict) -> None:
    conn.execute(
        "INSERT INTO journal (op_key, event, details_json, created_at)"
        " VALUES (?, ?, ?, ?)",
        (op_key, event, json.dumps(details, sort_keys=True), _db.utcnow()),
    )


def reserve_replacement(db_path: str | Path, *, case_id: str, run_id: str,
                        op_key: str, order_id: str, order_item_id: str,
                        size: str, qty: int = 1) -> ReservationResult:
    """Reserve one replacement unit of the exact requested size.

    Idempotent on op_key: same key plus same payload returns the saved
    result; same key plus different payload raises PayloadMismatchError.
    A different key for an item that already has an active exchange
    returns the existing exchange as a duplicate without new writes.
    Validation failures raise and leave inventory unchanged.
    """
    if qty < 1:
        raise ReservationError("qty must be at least 1")
    payload = {"order_id": order_id, "order_item_id": order_item_id,
               "size": size, "qty": qty}
    digest = payload_hash(payload)
    conn = _db.connect(db_path)
    try:
        with _db.immediate(conn):
            saved = conn.execute(
                "SELECT * FROM operations WHERE idempotency_key = ?",
                (op_key,)).fetchone()
            if saved is not None:
                if saved["payload_hash"] != digest:
                    raise PayloadMismatchError(
                        f"op_key {op_key!r} was already used with a "
                        "different payload")
                result = json.loads(saved["result_json"])
                return ReservationResult(
                    exchange_id=result["exchange_id"],
                    status=result["status"],
                    duplicate=result.get("duplicate", False))

            item_row = conn.execute(
                "SELECT * FROM order_items WHERE id = ?", (order_item_id,)
            ).fetchone()
            if item_row is None or item_row["order_id"] != order_id:
                raise ItemNotFoundError(
                    f"item {order_item_id!r} not found on order {order_id!r}")
            item = _row_to_item(item_row)

            eligible, reason = check_eligibility(item, date.today())
            if not eligible:
                raise IneligibleError(reason)

            existing = get_active_exchange(conn, order_item_id)
            if existing is not None:
                result = {"exchange_id": existing.id,
                          "status": existing.status, "duplicate": True}
                now = _db.utcnow()
                conn.execute(
                    """INSERT INTO operations
                       (idempotency_key, case_id, run_id, op_type,
                        payload_hash, payload_json, status, result_json,
                        created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (op_key, case_id, run_id, OP_RESERVE, digest,
                     json.dumps(payload, sort_keys=True), "duplicate",
                     json.dumps(result), now, now),
                )
                _journal(conn, op_key, "duplicate_reused",
                         {"exchange_id": existing.id,
                          "order_item_id": order_item_id})
                return ReservationResult(exchange_id=existing.id,
                                         status=existing.status,
                                         duplicate=True)

            stock = conn.execute(
                "SELECT * FROM stock WHERE sku = ? AND size = ?",
                (item.sku, size)).fetchone()
            available = (stock["on_hand"] - stock["held"]
                         if stock is not None else 0)
            if stock is None or available < qty:
                raise InsufficientStockError(
                    f"only {available} unit(s) of {item.sku} size {size} "
                    "available; the requested size is never substituted")

            count = conn.execute(
                "SELECT COUNT(*) AS n FROM exchanges WHERE order_item_id = ?",
                (order_item_id,)).fetchone()["n"]
            exchange_id = f"EXC-{order_item_id}-{count + 1}"
            now = _db.utcnow()
            conn.execute(
                """INSERT INTO exchanges
                   (id, case_id, order_id, order_item_id, requested_size,
                    authorized_size, qty, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (exchange_id, case_id, order_id, order_item_id, size,
                 size, qty, "replacement_reserved", now, now),
            )
            conn.execute(
                "UPDATE stock SET held = held + ? WHERE sku = ? AND size = ?",
                (qty, item.sku, size),
            )
            result = {"exchange_id": exchange_id,
                      "status": "replacement_reserved", "duplicate": False}
            conn.execute(
                """INSERT INTO operations
                   (idempotency_key, case_id, run_id, op_type, payload_hash,
                    payload_json, status, result_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (op_key, case_id, run_id, OP_RESERVE, digest,
                 json.dumps(payload, sort_keys=True), "committed",
                 json.dumps(result), now, now),
            )
            _journal(conn, op_key, "reserved",
                     {"exchange_id": exchange_id,
                      "order_item_id": order_item_id,
                      "sku": item.sku, "size": size, "qty": qty})
            return ReservationResult(exchange_id=exchange_id,
                                     status="replacement_reserved",
                                     duplicate=False)
    finally:
        conn.close()


def get_operation_status(db_path: str | Path,
                         op_key: str) -> dict | None:
    """Return the saved operation record, or None when unknown.

    None means unknown, not proof of no effect. Callers must re-query;
    they must never assume a fresh key is safe on an uncertain write.
    """
    conn = _db.connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM operations WHERE idempotency_key = ?",
            (op_key,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {"idempotency_key": row["idempotency_key"],
            "case_id": row["case_id"], "run_id": row["run_id"],
            "op_type": row["op_type"], "status": row["status"],
            "payload": json.loads(row["payload_json"]),
            "result": json.loads(row["result_json"])}
