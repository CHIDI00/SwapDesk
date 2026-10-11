"""Agent-facing tools: thin, typed wrappers over operations.

One concern only: translating backend results (and backend errors) into
JSON the model can act on. All safety rules live in operations.py; these
wrappers add no policy of their own.

Key discipline is structural: each tool derives its idempotency key from
(case_id, run_id, tool, attempt). Retrying the same tool reuses the key
automatically. A fresh key needs an explicit attempt number, so the model
can never mint one by accident after an uncertain write.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import neatlogs
from langchain_core.tools import tool

from .. import operations as _ops


@dataclass(frozen=True)
class ToolContext:
    db_path: str | Path
    case_id: str
    run_id: str
    order_id: str | None = None
    order_item_id: str | None = None
    requested_size: str | None = None
    qty: int = 1


def _key(ctx: ToolContext, name: str, attempt: int = 1) -> str:
    base = f"{ctx.case_id}:{ctx.run_id}:{name}"
    return base if attempt <= 1 else f"{base}#a{attempt}"


def _ok(**fields) -> str:
    return json.dumps({"ok": True, **fields}, sort_keys=True)


def _err(error: str, *, retry_same_key: bool = False,
         op_key: str | None = None) -> str:
    payload = {"ok": False, "error": error, "retry_same_key": retry_same_key}
    if op_key is not None:
        payload["op_key"] = op_key
    return json.dumps(payload, sort_keys=True)


_STOCK_CLAIM_PHRASES = (
    "out of stock",
    "out-of-stock",
    "unavailable",
    "sold out",
    "no stock",
    "not in stock",
    "only 0",
    "0 unit",
)


def _claims_unavailable(question: str) -> bool:
    """True only when the question asserts the size cannot be supplied.

    The guard rejects unsupported stock claims, not every clarification
    recorded while inventory happens to be available.
    """
    lowered = (question or "").lower()
    return any(phrase in lowered for phrase in _STOCK_CLAIM_PHRASES)


def build_tools(ctx: ToolContext) -> list:
    """Create the agent's tool list bound to one case run."""
    db = ctx.db_path
    case_id, run_id = ctx.case_id, ctx.run_id

    @tool
    @neatlogs.span(kind="TOOL", tool_name="get_order")
    def get_order(order_id: str) -> str:
        """Look up an order and its items. Returns null when unknown."""
        conn = _ops._db.connect(db)
        try:
            order = _ops.get_order(conn, order_id)
            if order is None:
                return _ok(order=None)
            items = [dict(r) for r in conn.execute(
                "SELECT * FROM order_items WHERE order_id = ?",
                (order_id,)).fetchall()]
        finally:
            conn.close()
        return _ok(order={"id": order.id,
                          "customer_ref": order.customer_ref},
                   items=[{k: i[k] for k in (
                       "id", "sku", "size", "qty", "status", "delivered_at",
                       "final_sale")} for i in items])

    @tool
    @neatlogs.span(kind="TOOL", tool_name="get_return_policy")
    def get_return_policy() -> str:
        """Read the shop's return policy window and exclusions."""
        return _ok(policy=_ops.get_return_policy())

    @tool
    @neatlogs.span(kind="TOOL", tool_name="find_exchange_stock")
    def find_exchange_stock(sku: str, size: str) -> str:
        """Check available units of a SKU/size pool."""
        conn = _ops._db.connect(db)
        try:
            level = _ops.find_exchange_stock(conn, sku, size)
        finally:
            conn.close()
        if level is None:
            return _ok(pool=None)
        return _ok(pool={"sku": sku, "size": size,
                         "on_hand": level.on_hand, "held": level.held,
                         "available": level.available})

    @tool
    @neatlogs.span(kind="TOOL", tool_name="get_active_exchange")
    def get_active_exchange(order_item_id: str) -> str:
        """Return the open exchange for an item, if any."""
        conn = _ops._db.connect(db)
        try:
            found = _ops.get_active_exchange(conn, order_item_id)
        finally:
            conn.close()
        if found is None:
            return _ok(exchange=None)
        return _ok(exchange={"id": found.id, "status": found.status,
                             "authorized_size": found.authorized_size})

    @tool
    @neatlogs.span(kind="TOOL", tool_name="get_operation_status")
    def get_operation_status(op_key: str) -> str:
        """Re-query a past operation by key. Null means unknown: never
        assume a fresh key is safe on an uncertain write."""
        status = _ops.get_operation_status(db, op_key)
        return _ok(operation=status)

    @tool
    @neatlogs.span(kind="TOOL", tool_name="verify_exchange")
    def verify_exchange(exchange_id: str) -> str:
        """Read-only recovery handoff for an exchange."""
        try:
            hand = _ops.verify_exchange(db, exchange_id)
        except _ops.ExchangeNotFoundError as exc:
            return _err(str(exc))
        return _ok(exchange_id=hand.exchange_id, case_id=hand.case_id,
                   status=hand.status, return_id=hand.return_id,
                   label_id=hand.label_id, tracking_ref=hand.tracking_ref,
                   hold_active=hand.hold_active,
                   pending_cleanup=hand.pending_cleanup,
                   consistent=hand.consistent,
                   suggested_next=hand.suggested_next)

    @tool
    @neatlogs.span(kind="TOOL", tool_name="reserve_replacement")
    def reserve_replacement(order_id: str, order_item_id: str, size: str,
                            qty: int = 1, requested_size: str | None = None,
                            consent: bool = False,
                            attempt: int = 1) -> str:
        """Hold one replacement unit of the exact size. Pass
        requested_size plus consent=true only when the customer
        explicitly accepted a different size."""
        key = _key(ctx, "reserve", attempt)
        try:
            res = _ops.reserve_replacement(
                db, case_id=case_id, run_id=run_id, op_key=key,
                order_id=order_id, order_item_id=order_item_id, size=size,
                qty=qty, requested_size=requested_size, consent=consent)
        except (_ops.TransientError, _ops.WorkerCrashedError) as exc:
            return _err(str(exc), retry_same_key=True, op_key=key)
        except _ops.OperationError as exc:
            return _err(str(exc), op_key=key)
        except _ops.ReservationError as exc:
            return _err(str(exc), op_key=key)
        return _ok(exchange_id=res.exchange_id, status=res.status,
                   duplicate=res.duplicate, op_key=key)

    @tool
    @neatlogs.span(kind="TOOL", tool_name="create_return")
    def create_return(exchange_id: str, attempt: int = 1) -> str:
        """Create the return record for a reserved exchange."""
        key = _key(ctx, "return", attempt)
        try:
            res = _ops.create_return(db, case_id=case_id, run_id=run_id,
                                     op_key=key, exchange_id=exchange_id)
        except (_ops.TransientError,) as exc:
            return _err(str(exc), retry_same_key=True, op_key=key)
        except _ops.OperationError as exc:
            return _err(str(exc), op_key=key)
        return _ok(exchange_id=res.exchange_id, return_id=res.return_id,
                   status=res.status, duplicate=res.duplicate, op_key=key)

    @tool
    @neatlogs.span(kind="TOOL", tool_name="create_label")
    def create_label(exchange_id: str, attempt: int = 1) -> str:
        """Create the mock shipping label for a returned exchange."""
        key = _key(ctx, "label", attempt)
        try:
            res = _ops.create_label(db, case_id=case_id, run_id=run_id,
                                    op_key=key, exchange_id=exchange_id)
        except (_ops.TransientError, _ops.LabelTimeoutError) as exc:
            return _err(str(exc), retry_same_key=True, op_key=key)
        except _ops.OperationError as exc:
            return _err(str(exc), op_key=key)
        return _ok(exchange_id=res.exchange_id, label_id=res.label_id,
                   tracking_ref=res.tracking_ref, status=res.status,
                   duplicate=res.duplicate, op_key=key)

    @tool
    @neatlogs.span(kind="TOOL", tool_name="finalize_arranged")
    def finalize_arranged(exchange_id: str, attempt: int = 1) -> str:
        """Verify return plus label plus hold, then mark arranged."""
        key = _key(ctx, "finalize", attempt)
        try:
            res = _ops.finalize_arranged(db, case_id=case_id, run_id=run_id,
                                         op_key=key, exchange_id=exchange_id)
        except (_ops.TransientError,) as exc:
            return _err(str(exc), retry_same_key=True, op_key=key)
        except _ops.OperationError as exc:
            return _err(str(exc), op_key=key)
        return _ok(exchange_id=res.exchange_id, status=res.status,
                   duplicate=res.duplicate, op_key=key)

    @tool
    @neatlogs.span(kind="TOOL", tool_name="escalate_to_human")
    def escalate_to_human(exchange_id: str, reason: str,
                          attempt: int = 1) -> str:
        """Hand the case to a human: releases held stock, keeps history."""
        key = _key(ctx, "escalate", attempt)
        try:
            res = _ops.escalate_case(db, case_id=case_id, run_id=run_id,
                                     op_key=key, exchange_id=exchange_id,
                                     reason=reason)
        except (_ops.TransientError, _ops.ReleaseFailedError) as exc:
            return _err(str(exc), retry_same_key=True, op_key=key)
        except _ops.OperationError as exc:
            return _err(str(exc), op_key=key)
        return _ok(exchange_id=res.exchange_id, status=res.status,
                   hold_released=res.hold_released,
                   duplicate=res.duplicate, op_key=key)

    @tool
    @neatlogs.span(kind="TOOL", tool_name="cancel_exchange")
    def cancel_exchange(exchange_id: str, reason: str = "",
                        attempt: int = 1) -> str:
        """Cancel an exchange, releasing held stock. A later attempt may
        start fresh with a higher attempt number."""
        key = _key(ctx, "cancel", attempt)
        try:
            res = _ops.cancel_exchange(db, case_id=case_id, run_id=run_id,
                                       op_key=key, exchange_id=exchange_id,
                                       reason=reason)
        except (_ops.TransientError,) as exc:
            return _err(str(exc), retry_same_key=True, op_key=key)
        except _ops.OperationError as exc:
            return _err(str(exc), op_key=key)
        return _ok(exchange_id=res.exchange_id, status=res.status,
                   hold_released=res.hold_released,
                   duplicate=res.duplicate, op_key=key)

    @tool
    @neatlogs.span(kind="TOOL", tool_name="record_denial")
    def record_denial(reason: str) -> str:
        """Record a policy denial. Writes no fulfillment rows. The reason
        must quote the observed fact and cannot be empty."""
        try:
            _ops.note_case(db, case_id=case_id, state="denied",
                           detail=reason)
        except _ops.OperationError as exc:
            return _err(str(exc))
        return _ok(state="denied")

    @tool
    @neatlogs.span(kind="TOOL", tool_name="record_clarification")
    def record_clarification(question: str) -> str:
        """Record what is needed from the customer. Writes no rows. The
        question must state what is missing and cannot be empty."""
        if (ctx.order_id and ctx.order_item_id and ctx.requested_size
                and _claims_unavailable(question)):
            conn = _ops._db.connect(db)
            try:
                item_row = conn.execute(
                    "SELECT * FROM order_items WHERE id = ? AND order_id = ?",
                    (ctx.order_item_id, ctx.order_id)).fetchone()
                if item_row is not None:
                    eligible, _ = _ops.check_eligibility(
                        _ops._row_to_item(item_row), date.today())
                    pool = _ops.find_exchange_stock(
                        conn, item_row["sku"], ctx.requested_size)
                    if eligible and pool is not None and pool.available >= ctx.qty:
                        return _err(
                            "cannot claim the requested size is unavailable: "
                            f"backend inventory confirms {pool.available} "
                            "unit(s) available; continue with the exact "
                            "requested size")
            finally:
                conn.close()
        try:
            _ops.note_case(db, case_id=case_id, state="needs_information",
                           detail=question)
        except _ops.OperationError as exc:
            return _err(str(exc))
        return _ok(state="needs_information")

    @tool
    @neatlogs.span(kind="TOOL", tool_name="escalate_without_exchange")
    def escalate_without_exchange(reason: str, attempt: int = 1) -> str:
        """Escalate when no exchange was started (no stock to release).
        For partial state with a held unit, use escalate_to_human."""
        key = _key(ctx, "escalate", attempt)
        try:
            res = _ops.record_escalation(db, case_id=case_id, run_id=run_id,
                                         op_key=key, reason=reason)
        except (_ops.TransientError,) as exc:
            return _err(str(exc), retry_same_key=True, op_key=key)
        except _ops.OperationError as exc:
            return _err(str(exc), op_key=key)
        return _ok(exchange_id=res.exchange_id, status=res.status,
                   duplicate=res.duplicate, op_key=key)

    return [get_order, get_return_policy, find_exchange_stock,
            get_active_exchange, get_operation_status, verify_exchange,
            reserve_replacement, create_return, create_label,
            finalize_arranged, escalate_to_human, cancel_exchange,
            record_denial, record_clarification, escalate_without_exchange]
