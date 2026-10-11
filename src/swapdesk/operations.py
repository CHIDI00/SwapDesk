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
from . import faults as _faults
from .models import (
    CASE_STATES,
    EXCHANGE_TRANSITIONS,
    OP_ARRANGE,
    OP_CANCEL,
    OP_ESCALATE,
    OP_LABEL,
    OP_RELEASE,
    OP_RESERVE,
    OP_RETURN,
    TERMINAL_EXCHANGE_STATUSES,
    ExchangeHandoff,
    ExchangeRecord,
    EscalationResult,
    FinalizeResult,
    LabelResult,
    Order,
    OrderItem,
    ReleaseResult,
    ReservationResult,
    ReturnResult,
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


class OperationError(Exception):
    """Base class for Slice 2 operation failures."""


class TransientError(OperationError):
    """Injected pre-commit transient. Nothing was written; retry same key."""


class WorkerCrashedError(OperationError):
    """State committed, then the worker died. Re-query status, same key."""


class LabelTimeoutError(OperationError):
    """Label committed, then the response timed out. Same key to recover."""


class ReleaseFailedError(OperationError):
    """Cleanup did not complete; exchange is cleanup_pending. Same key."""


class IllegalTransitionError(OperationError):
    """The requested state move is not legal. Nothing was written."""


class ExchangeNotFoundError(OperationError):
    """Unknown exchange id. Nothing was written."""


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
        hold_released=bool(row["hold_released"]) if "hold_released" in row.keys() else False,
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


def _load_saved(conn: sqlite3.Connection, op_key: str,
                digest: str) -> sqlite3.Row | None:
    """Return the saved op row, or None. Digest mismatch always raises."""
    saved = conn.execute(
        "SELECT * FROM operations WHERE idempotency_key = ?",
        (op_key,)).fetchone()
    if saved is None:
        return None
    if saved["payload_hash"] != digest:
        raise PayloadMismatchError(
            f"op_key {op_key!r} was already used with a different payload; "
            "re-query status instead of minting a fresh key")
    return saved


def _record_op(conn: sqlite3.Connection, *, op_key: str, case_id: str,
               run_id: str, op_type: str, digest: str, payload: dict,
               status: str, result: dict) -> None:
    now = _db.utcnow()
    conn.execute(
        """INSERT INTO operations
           (idempotency_key, case_id, run_id, op_type, payload_hash,
            payload_json, status, result_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (op_key, case_id, run_id, op_type, digest,
         json.dumps(payload, sort_keys=True), status,
         json.dumps(result), now, now),
    )


def _write_op(conn: sqlite3.Connection, saved: sqlite3.Row | None, *,
              op_key: str, case_id: str, run_id: str, op_type: str,
              digest: str, payload: dict, status: str, result: dict) -> None:
    """INSERT a fresh op row, or UPDATE a retried failed one (same key)."""
    if saved is None:
        _record_op(conn, op_key=op_key, case_id=case_id, run_id=run_id,
                   op_type=op_type, digest=digest, payload=payload,
                   status=status, result=result)
        return
    conn.execute(
        """UPDATE operations SET status = ?, result_json = ?,
           updated_at = ? WHERE idempotency_key = ?""",
        (status, json.dumps(result), _db.utcnow(), op_key),
    )


def _touch_case(conn: sqlite3.Connection, case_id: str, state: str,
                step: str | None = None,
                note: str | None = None) -> None:
    """Persist case progress in the same transaction as the business write."""
    if state not in CASE_STATES:
        raise OperationError(f"unknown case state {state!r}")
    row = conn.execute("SELECT * FROM cases WHERE case_id = ?",
                       (case_id,)).fetchone()
    progress: dict = json.loads(row["progress_json"]) if row else {}
    progress["attempts"] = progress.get("attempts", 0) + 1
    steps = progress.setdefault("steps", [])
    if step is not None and step not in steps:
        steps.append(step)
    if note is not None:
        progress.setdefault("notes", []).append(
            {"state": state, "detail": note, "at": _db.utcnow()})
    now = _db.utcnow()
    conn.execute(
        """INSERT INTO cases (case_id, state, progress_json, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(case_id) DO UPDATE SET state = excluded.state,
             progress_json = excluded.progress_json,
             updated_at = excluded.updated_at""",
        (case_id, state, json.dumps(progress, sort_keys=True), now),
    )


def _require_exchange(conn: sqlite3.Connection,
                      exchange_id: str) -> ExchangeRecord:
    row = conn.execute("SELECT * FROM exchanges WHERE id = ?",
                       (exchange_id,)).fetchone()
    if row is None:
        raise ExchangeNotFoundError(f"exchange {exchange_id!r} not found")
    return _row_to_exchange(row)


def _latest_exchange(conn: sqlite3.Connection,
                     order_item_id: str) -> ExchangeRecord | None:
    row = conn.execute(
        "SELECT * FROM exchanges WHERE order_item_id = ?"
        " ORDER BY rowid DESC LIMIT 1",
        (order_item_id,)).fetchone()
    return _row_to_exchange(row) if row else None


def _record_duplicate(conn: sqlite3.Connection, *, op_key: str, case_id: str,
                      run_id: str, op_type: str, digest: str, payload: dict,
                      exchange: ExchangeRecord) -> dict:
    """Reuse an existing exchange without any new stock effect."""
    result = {"exchange_id": exchange.id, "status": exchange.status,
              "duplicate": True}
    _record_op(conn, op_key=op_key, case_id=case_id, run_id=run_id,
               op_type=op_type, digest=digest, payload=payload,
               status="duplicate", result=result)
    _journal(conn, op_key, "duplicate_reused",
             {"exchange_id": exchange.id,
              "order_item_id": exchange.order_item_id})
    _touch_case(conn, case_id, exchange.status)
    return result


def _transition(conn: sqlite3.Connection, *, exchange_id: str, to_status: str,
                op_key: str, event: str, extra: dict | None = None,
                case_step: str | None = None) -> ExchangeRecord:
    """Move an exchange one legal step; raises IllegalTransitionError."""
    current = _require_exchange(conn, exchange_id)
    allowed = EXCHANGE_TRANSITIONS.get(current.status, frozenset())
    if to_status not in allowed:
        raise IllegalTransitionError(
            f"cannot move exchange {exchange_id!r} from {current.status!r} "
            f"to {to_status!r}; re-query status and continue from the "
            "persisted state")
    now = _db.utcnow()
    conn.execute("UPDATE exchanges SET status = ?, updated_at = ? WHERE id = ?",
                 (to_status, now, exchange_id))
    _touch_case(conn, current.case_id, to_status, step=case_step)
    details = {"exchange_id": exchange_id, "from": current.status,
               "to": to_status}
    details.update(extra or {})
    _journal(conn, op_key, event, details)
    return _require_exchange(conn, exchange_id)


def reserve_replacement(db_path: str | Path, *, case_id: str, run_id: str,
                        op_key: str, order_id: str, order_item_id: str,
                        size: str, qty: int = 1,
                        requested_size: str | None = None,
                        consent: bool = False) -> ReservationResult:
    """Reserve one replacement unit of the exact requested size.

    `size` is the authorized size (never substituted silently);
    `requested_size` records what the customer originally asked for and
    defaults to `size`. Authorizing a different size requires explicit
    recorded customer consent, otherwise this raises and writes nothing.
    All three join the idempotency payload.

    Idempotent on op_key: same key plus same payload returns the saved
    result; same key plus different payload raises PayloadMismatchError.
    A different key for an item that already has an active exchange
    returns the existing exchange as a duplicate without new writes.
    Validation failures raise and leave inventory unchanged.
    """
    if qty < 1:
        raise ReservationError("qty must be at least 1")
    if requested_size is None:
        requested_size = size
    if requested_size != size and not consent:
        raise ReservationError(
            f"size {size!r} differs from requested {requested_size!r} "
            "without recorded customer consent; refusing to substitute")
    payload = {"order_id": order_id, "order_item_id": order_item_id,
               "size": size, "qty": qty, "requested_size": requested_size,
               "consent": consent}
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

            if _faults.consume(op_key, "transient"):
                raise TransientError(
                    f"injected transient failure for op_key {op_key!r}; "
                    "nothing was written, retry with the same key")

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
                dup = _record_duplicate(
                    conn, op_key=op_key, case_id=case_id, run_id=run_id,
                    op_type=OP_RESERVE, digest=digest, payload=payload,
                    exchange=existing)
                return ReservationResult(exchange_id=dup["exchange_id"],
                                         status=dup["status"], duplicate=True)

            latest = _latest_exchange(conn, order_item_id)
            if latest is not None and latest.status in ("arranged",
                                                        "escalated"):
                # A finished exchange stays the answer: reuse it with no new
                # stock effect. Cancelled/denied rows allow a fresh attempt.
                dup = _record_duplicate(
                    conn, op_key=op_key, case_id=case_id, run_id=run_id,
                    op_type=OP_RESERVE, digest=digest, payload=payload,
                    exchange=latest)
                return ReservationResult(exchange_id=dup["exchange_id"],
                                         status=dup["status"], duplicate=True)

            stock = conn.execute(
                "SELECT * FROM stock WHERE sku = ? AND size = ?",
                (item.sku, size)).fetchone()
            available = (stock["on_hand"] - stock["held"]
                         if stock is not None else 0)
            if _faults.consume(op_key, "deplete_stock"):
                # Simulate the pool draining between lookup and write. The
                # depletion rolls back with this failed transaction.
                conn.execute(
                    "UPDATE stock SET on_hand = held WHERE sku = ? AND size = ?",
                    (item.sku, size))
                available = 0
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
                (exchange_id, case_id, order_id, order_item_id,
                 requested_size, size, qty, "replacement_reserved", now, now),
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
                      "sku": item.sku, "size": size, "qty": qty,
                      "requested_size": requested_size})
            _touch_case(conn, case_id, "replacement_reserved",
                        step="reserved",
                        note=(f"consent:{size}"
                              if requested_size != size and consent
                              else None))
            fresh = ReservationResult(exchange_id=exchange_id,
                                      status="replacement_reserved",
                                      duplicate=False)
        if _faults.consume(op_key, "crash"):
            # The transaction above already committed: the caller sees a
            # crash, but get_operation_status(op_key) reports committed.
            raise WorkerCrashedError(
                f"worker crashed after committing op_key {op_key!r}; "
                "re-query status and retry with the same key")
        return fresh
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


def create_return(db_path: str | Path, *, case_id: str, run_id: str,
                  op_key: str, exchange_id: str) -> ReturnResult:
    """Create the mock return for a reserved exchange.

    Idempotent on op_key. A different key after the return exists is
    rejected: re-query status and reuse the original key.
    """
    payload = {"exchange_id": exchange_id}
    digest = payload_hash(payload)
    conn = _db.connect(db_path)
    try:
        with _db.immediate(conn):
            saved = _load_saved(conn, op_key, digest)
            if saved is not None:
                result = json.loads(saved["result_json"])
                return ReturnResult(
                    exchange_id=result["exchange_id"],
                    return_id=result["return_id"],
                    status=result["status"], duplicate=True)
            if _faults.consume(op_key, "transient"):
                raise TransientError(
                    f"injected transient failure for op_key {op_key!r}; "
                    "nothing was written, retry with the same key")
            exchange = _require_exchange(conn, exchange_id)
            if "return_created" not in EXCHANGE_TRANSITIONS.get(
                    exchange.status, frozenset()):
                raise IllegalTransitionError(
                    f"exchange {exchange_id!r} is {exchange.status!r}, "
                    "not reserved; re-query status instead of minting a "
                    "fresh key")
            return_id = f"RET-{exchange_id}"
            now = _db.utcnow()
            conn.execute(
                """INSERT INTO returns
                   (id, exchange_id, case_id, order_item_id, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (return_id, exchange_id, exchange.case_id,
                 exchange.order_item_id, now),
            )
            _transition(conn, exchange_id=exchange_id,
                        to_status="return_created", op_key=op_key,
                        event="return_created",
                        extra={"return_id": return_id}, case_step="returned")
            result = {"exchange_id": exchange_id, "return_id": return_id,
                      "status": "return_created", "duplicate": False}
            _record_op(conn, op_key=op_key, case_id=case_id, run_id=run_id,
                       op_type=OP_RETURN, digest=digest, payload=payload,
                       status="committed", result=result)
            return ReturnResult(exchange_id=exchange_id, return_id=return_id,
                                status="return_created", duplicate=False)
    finally:
        conn.close()


def create_label(db_path: str | Path, *, case_id: str, run_id: str,
                 op_key: str, exchange_id: str) -> LabelResult:
    """Create the mock shipping label for a returned exchange.

    Idempotent on op_key. An armed "timeout" fault commits the label and
    then raises: the caller must re-query status and retry the same key.
    """
    payload = {"exchange_id": exchange_id}
    digest = payload_hash(payload)
    conn = _db.connect(db_path)
    try:
        with _db.immediate(conn):
            saved = _load_saved(conn, op_key, digest)
            if saved is not None:
                result = json.loads(saved["result_json"])
                return LabelResult(
                    exchange_id=result["exchange_id"],
                    label_id=result["label_id"],
                    tracking_ref=result["tracking_ref"],
                    status=result["status"], duplicate=True)
            if _faults.consume(op_key, "transient"):
                raise TransientError(
                    f"injected transient failure for op_key {op_key!r}; "
                    "nothing was written, retry with the same key")
            exchange = _require_exchange(conn, exchange_id)
            if "label_created" not in EXCHANGE_TRANSITIONS.get(
                    exchange.status, frozenset()):
                raise IllegalTransitionError(
                    f"exchange {exchange_id!r} is {exchange.status!r}, "
                    "not return_created; re-query status instead of minting "
                    "a fresh key")
            label_id = f"LBL-{exchange_id}"
            tracking_ref = f"TRK-MOCK-{exchange_id}"
            now = _db.utcnow()
            ret = conn.execute("SELECT * FROM returns WHERE exchange_id = ?",
                               (exchange_id,)).fetchone()
            if ret is None:
                raise OperationError(
                    f"exchange {exchange_id!r} is return_created but has no "
                    "return row; data is inconsistent, refusing to label")
            conn.execute(
                """INSERT INTO labels (id, return_id, exchange_id,
                   tracking_ref, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (label_id, ret["id"], exchange_id, tracking_ref, now),
            )
            _transition(conn, exchange_id=exchange_id,
                        to_status="label_created", op_key=op_key,
                        event="label_created",
                        extra={"label_id": label_id,
                               "tracking_ref": tracking_ref},
                        case_step="labeled")
            result = {"exchange_id": exchange_id, "label_id": label_id,
                      "tracking_ref": tracking_ref,
                      "status": "label_created", "duplicate": False}
            _record_op(conn, op_key=op_key, case_id=case_id, run_id=run_id,
                       op_type=OP_LABEL, digest=digest, payload=payload,
                       status="committed", result=result)
            out = LabelResult(exchange_id=exchange_id, label_id=label_id,
                              tracking_ref=tracking_ref,
                              status="label_created", duplicate=False)
        if _faults.consume(op_key, "timeout"):
            # The label above already committed: the response is lost, not
            # the effect. Same key to recover; exactly one label exists.
            raise LabelTimeoutError(
                f"label response timed out for op_key {op_key!r} after "
                "commit; re-query status and retry with the same key")
        return out
    finally:
        conn.close()


def finalize_arranged(db_path: str | Path, *, case_id: str, run_id: str,
                      op_key: str, exchange_id: str) -> FinalizeResult:
    """Verify return plus label plus hold, then mark the exchange arranged.

    Finalizing consumes the hold into a mock shipment (held and on_hand
    both drop), so no orphan hold survives a completed exchange.
    """
    payload = {"exchange_id": exchange_id}
    digest = payload_hash(payload)
    conn = _db.connect(db_path)
    try:
        with _db.immediate(conn):
            saved = _load_saved(conn, op_key, digest)
            if saved is not None:
                result = json.loads(saved["result_json"])
                return FinalizeResult(exchange_id=result["exchange_id"],
                                      status=result["status"], duplicate=True)
            if _faults.consume(op_key, "transient"):
                raise TransientError(
                    f"injected transient failure for op_key {op_key!r}; "
                    "nothing was written, retry with the same key")
            exchange = _require_exchange(conn, exchange_id)
            if "arranged" not in EXCHANGE_TRANSITIONS.get(
                    exchange.status, frozenset()):
                raise IllegalTransitionError(
                    f"exchange {exchange_id!r} is {exchange.status!r}, "
                    "not label_created; re-query status instead of minting "
                    "a fresh key")
            ret = conn.execute("SELECT * FROM returns WHERE exchange_id = ?",
                               (exchange_id,)).fetchone()
            lab = conn.execute("SELECT * FROM labels WHERE exchange_id = ?",
                               (exchange_id,)).fetchone()
            if ret is None or lab is None:
                raise OperationError(
                    f"exchange {exchange_id!r} is label_created but return "
                    "or label rows are missing; refusing to arrange")
            item_row = conn.execute(
                "SELECT * FROM order_items WHERE id = ?",
                (exchange.order_item_id,)).fetchone()
            if item_row is None:
                raise OperationError(
                    f"order item {exchange.order_item_id!r} vanished; "
                    "refusing to arrange")
            stock = conn.execute(
                "SELECT * FROM stock WHERE sku = ? AND size = ?",
                (item_row["sku"], exchange.authorized_size)).fetchone()
            if stock is None or stock["held"] < exchange.qty:
                raise OperationError(
                    f"stock hold missing for exchange {exchange_id!r}; "
                    "refusing to arrange")
            conn.execute(
                "UPDATE stock SET held = held - ?, on_hand = on_hand - ?"
                " WHERE sku = ? AND size = ?",
                (exchange.qty, exchange.qty, item_row["sku"],
                 exchange.authorized_size),
            )
            conn.execute("UPDATE exchanges SET hold_released = 1 WHERE id = ?",
                         (exchange_id,))
            _transition(conn, exchange_id=exchange_id, to_status="arranged",
                        op_key=op_key, event="arranged",
                        extra={"return_id": ret["id"],
                               "label_id": lab["id"]},
                        case_step="arranged")
            result = {"exchange_id": exchange_id, "status": "arranged",
                      "duplicate": False}
            _record_op(conn, op_key=op_key, case_id=case_id, run_id=run_id,
                       op_type=OP_ARRANGE, digest=digest, payload=payload,
                       status="committed", result=result)
            return FinalizeResult(exchange_id=exchange_id, status="arranged",
                                  duplicate=False)
    finally:
        conn.close()


def release_reservation(db_path: str | Path, *, case_id: str, run_id: str,
                        op_key: str, exchange_id: str,
                        end_state: str = "escalated", reason: str = "",
                        op_type: str = OP_RELEASE) -> ReleaseResult:
    """Release a held unit idempotently, closing the exchange.

    A repeated release (same or different key) never decrements twice:
    once the hold flag is set, further calls are recorded no-ops. An
    armed "release_fail" fault persists cleanup_pending and raises, so a
    failed cleanup stays visible until the same key retries cleanly.
    """
    if end_state not in ("escalated", "cancelled"):
        raise OperationError(
            f"release end_state must be 'escalated' or 'cancelled', "
            f"got {end_state!r}")
    payload = {"exchange_id": exchange_id, "end_state": end_state}
    digest = payload_hash(payload)
    conn = _db.connect(db_path)
    try:
        with _db.immediate(conn):
            saved = _load_saved(conn, op_key, digest)
            if (saved is not None
                    and json.loads(saved["result_json"]).get("cleanup")
                    != "pending"):
                result = json.loads(saved["result_json"])
                return ReleaseResult(
                    exchange_id=result["exchange_id"],
                    status=result["status"],
                    duplicate=result.get("duplicate", False),
                    hold_released=result.get("hold_released", True))
            exchange = _require_exchange(conn, exchange_id)
            if exchange.hold_released:
                result = {"exchange_id": exchange_id,
                          "status": exchange.status, "duplicate": True,
                          "hold_released": True}
                if saved is None:
                    _record_op(conn, op_key=op_key, case_id=case_id,
                               run_id=run_id, op_type=op_type, digest=digest,
                               payload=payload, status="duplicate",
                               result=result)
                    _journal(conn, op_key, "duplicate_reused",
                             {"exchange_id": exchange_id,
                              "note": "hold already released"})
                _touch_case(conn, case_id, exchange.status)
                return ReleaseResult(
                    exchange_id=exchange_id, status=exchange.status,
                    duplicate=True, hold_released=True)
            if _faults.consume(op_key, "transient"):
                raise TransientError(
                    f"injected transient failure for op_key {op_key!r}; "
                    "nothing was written, retry with the same key")
            failed = False
            if _faults.consume(op_key, "release_fail"):
                if exchange.status != "cleanup_pending":
                    _transition(conn, exchange_id=exchange_id,
                                to_status="cleanup_pending", op_key=op_key,
                                event="cleanup_pending",
                                extra={"reason": reason}, case_step="cleanup")
                result = {"exchange_id": exchange_id,
                          "status": "cleanup_pending", "duplicate": False,
                          "hold_released": False, "cleanup": "pending"}
                _write_op(conn, saved, op_key=op_key, case_id=case_id,
                          run_id=run_id, op_type=op_type, digest=digest,
                          payload=payload, status="failed", result=result)
                _journal(conn, op_key, "release_failed",
                         {"exchange_id": exchange_id, "reason": reason})
                failed = True
                out = ReleaseResult(exchange_id=exchange_id,
                                    status="cleanup_pending", duplicate=False,
                                    hold_released=False)
            else:
                if end_state not in EXCHANGE_TRANSITIONS.get(
                        exchange.status, frozenset()):
                    raise IllegalTransitionError(
                        f"exchange {exchange_id!r} is {exchange.status!r}; "
                        f"cannot release into {end_state!r}")
                item_row = conn.execute(
                    "SELECT * FROM order_items WHERE id = ?",
                    (exchange.order_item_id,)).fetchone()
                if item_row is None:
                    raise OperationError(
                        f"order item {exchange.order_item_id!r} vanished; "
                        "refusing to release")
                stock = conn.execute(
                    "SELECT * FROM stock WHERE sku = ? AND size = ?",
                    (item_row["sku"], exchange.authorized_size)).fetchone()
                if stock is None or stock["held"] < exchange.qty:
                    raise OperationError(
                        f"stock hold missing for exchange {exchange_id!r}; "
                        "refusing to release")
                conn.execute(
                    "UPDATE stock SET held = held - ?"
                    " WHERE sku = ? AND size = ?",
                    (exchange.qty, item_row["sku"],
                     exchange.authorized_size),
                )
                conn.execute(
                    "UPDATE exchanges SET hold_released = 1 WHERE id = ?",
                    (exchange_id,))
                _transition(conn, exchange_id=exchange_id,
                            to_status=end_state, op_key=op_key,
                            event="released",
                            extra={"reason": reason}, case_step="released")
                result = {"exchange_id": exchange_id, "status": end_state,
                          "duplicate": False, "hold_released": True}
                _write_op(conn, saved, op_key=op_key, case_id=case_id,
                          run_id=run_id, op_type=op_type, digest=digest,
                          payload=payload, status="committed", result=result)
                out = ReleaseResult(exchange_id=exchange_id, status=end_state,
                                    duplicate=False, hold_released=True)
        if failed:
            raise ReleaseFailedError(
                f"cleanup failed for exchange {exchange_id!r}; it is now "
                "cleanup_pending and stays visible until the same key "
                "retries cleanly")
        if _faults.consume(op_key, "crash"):
            raise WorkerCrashedError(
                f"worker crashed after committing op_key {op_key!r}; "
                "re-query status and retry with the same key")
        return out
    finally:
        conn.close()


def cancel_exchange(db_path: str | Path, *, case_id: str, run_id: str,
                    op_key: str, exchange_id: str,
                    reason: str = "") -> ReleaseResult:
    """Cancel an exchange, releasing any held stock.

    Cancelled is terminal but non-blocking: a later attempt for the same
    item starts a brand-new exchange with a new id.
    """
    return release_reservation(
        db_path, case_id=case_id, run_id=run_id, op_key=op_key,
        exchange_id=exchange_id, end_state="cancelled", reason=reason,
        op_type=OP_CANCEL)


def escalate_case(db_path: str | Path, *, case_id: str, run_id: str,
                  op_key: str, exchange_id: str,
                  reason: str) -> ReleaseResult:
    """Escalate to a human: release held stock and hand off partial state.

    Historical return/label rows stay for the audit; verify_exchange()
    reports them truthfully.
    """
    if not reason:
        raise OperationError("escalation requires a recorded reason")
    return release_reservation(
        db_path, case_id=case_id, run_id=run_id, op_key=op_key,
        exchange_id=exchange_id, end_state="escalated", reason=reason,
        op_type=OP_ESCALATE)


def record_escalation(db_path: str | Path, *, case_id: str, run_id: str,
                      op_key: str, reason: str) -> EscalationResult:
    """Escalate with no exchange started: nothing to release, handoff only.

    Idempotent on op_key with a journaled record, exactly like any other
    op. For partial state with a held unit, use escalate_case instead.
    """
    if not reason or not reason.strip():
        raise OperationError("escalation requires a recorded reason")
    payload = {"exchange_id": None, "reason": reason}
    digest = payload_hash(payload)
    conn = _db.connect(db_path)
    try:
        with _db.immediate(conn):
            saved = _load_saved(conn, op_key, digest)
            if saved is not None:
                return EscalationResult(exchange_id=None,
                                        status="escalated", duplicate=True)
            result = {"exchange_id": None, "status": "escalated",
                      "duplicate": False}
            _record_op(conn, op_key=op_key, case_id=case_id, run_id=run_id,
                       op_type=OP_ESCALATE, digest=digest, payload=payload,
                       status="committed", result=result)
            _journal(conn, op_key, "escalated",
                     {"exchange_id": None, "reason": reason})
            _touch_case(conn, case_id, "escalated", step="escalated",
                        note=reason)
            return EscalationResult(exchange_id=None, status="escalated",
                                    duplicate=False)
    finally:
        conn.close()


def note_case(db_path: str | Path, *, case_id: str, state: str,
              detail: str = "") -> dict:
    """Record case-level progress (received/needs_information/denied).

    Progress metadata only: no fulfillment effect, no idempotency key.
    Terminal-facing states (denied, needs_information, escalated)
    require a non-empty detail so handoffs are never blank.
    """
    if state not in CASE_STATES:
        raise OperationError(f"unknown case state {state!r}")
    if state in ("denied", "needs_information", "escalated"
                 ) and not detail.strip():
        raise OperationError(
            f"state {state!r} requires a non-empty detail; "
            "quote the observed fact (ids, sizes, policy phrase)")
    conn = _db.connect(db_path)
    try:
        with _db.immediate(conn):
            row = conn.execute("SELECT * FROM cases WHERE case_id = ?",
                               (case_id,)).fetchone()
            progress: dict = json.loads(row["progress_json"]) if row else {}
            notes = progress.setdefault("notes", [])
            notes.append({"state": state, "detail": detail,
                          "at": _db.utcnow()})
            now = _db.utcnow()
            conn.execute(
                """INSERT INTO cases (case_id, state, progress_json,
                   updated_at) VALUES (?, ?, ?, ?)
                   ON CONFLICT(case_id) DO UPDATE SET state = excluded.state,
                     progress_json = excluded.progress_json,
                     updated_at = excluded.updated_at""",
                (case_id, state, json.dumps(progress, sort_keys=True), now),
            )
            return {"case_id": case_id, "state": state}
    finally:
        conn.close()


def get_case(db_path: str | Path, case_id: str) -> dict | None:
    """Read saved case progress, or None when the case was never touched."""
    conn = _db.connect(db_path)
    try:
        row = conn.execute("SELECT * FROM cases WHERE case_id = ?",
                           (case_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {"case_id": row["case_id"], "state": row["state"],
            "progress": json.loads(row["progress_json"]),
            "updated_at": row["updated_at"]}


_SUGGESTED_NEXT = {
    "replacement_reserved": "create_return",
    "return_created": "create_label",
    "label_created": "finalize_arranged",
    "cleanup_pending": "release_reservation",
}


def verify_exchange(db_path: str | Path, exchange_id: str) -> ExchangeHandoff:
    """Read-only recovery handoff: persisted partial state, truthfully.

    Never writes. `suggested_next` names the op that continues from the
    persisted state, or "none" for terminal exchanges.
    """
    conn = _db.connect(db_path)
    try:
        exchange = _require_exchange(conn, exchange_id)
        ret = conn.execute("SELECT * FROM returns WHERE exchange_id = ?",
                           (exchange_id,)).fetchone()
        lab = conn.execute("SELECT * FROM labels WHERE exchange_id = ?",
                           (exchange_id,)).fetchone()
        item_row = conn.execute(
            "SELECT * FROM order_items WHERE id = ?",
            (exchange.order_item_id,)).fetchone()
        pool_ok = True
        if item_row is not None:
            stock = conn.execute(
                "SELECT * FROM stock WHERE sku = ? AND size = ?",
                (item_row["sku"], exchange.authorized_size)).fetchone()
            pool_ok = (stock is not None and stock["held"] >= 0
                       and stock["on_hand"] - stock["held"] >= 0)
    finally:
        conn.close()
    returned = ret is not None
    labeled = lab is not None
    status = exchange.status
    consistent = (not labeled or returned) and pool_ok
    if status == "replacement_reserved":
        consistent = consistent and not returned and not labeled
    elif status == "return_created":
        consistent = consistent and returned and not labeled
    elif status == "label_created":
        consistent = consistent and returned and labeled
    elif status == "arranged":
        consistent = (consistent and returned and labeled
                      and exchange.hold_released)
    hold_active = (not exchange.hold_released and status in (
        "replacement_reserved", "return_created", "label_created",
        "cleanup_pending"))
    return ExchangeHandoff(
        exchange_id=exchange_id, case_id=exchange.case_id, status=status,
        return_id=ret["id"] if ret else None,
        label_id=lab["id"] if lab else None,
        tracking_ref=lab["tracking_ref"] if lab else None,
        hold_active=hold_active,
        pending_cleanup=status == "cleanup_pending",
        consistent=consistent,
        suggested_next=_SUGGESTED_NEXT.get(status, "none"),
    )
