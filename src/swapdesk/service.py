"""Serving layer for the frontend demo: deterministic cases over SQLite.

No model, no queue. Requests execute synchronously (millisecond SQLite
transactions), so status reads are never blocked. Business rules stay in
operations.py; this module only sequences them with the documented demo
policy. Cases accumulate in one shared database; a restart reuses every
existing identity instead of reseeding.
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import uuid
from datetime import date
from pathlib import Path

from . import faults as _faults
from .agent.graph import (
    AgentContext,
    ConfigurationError,
    DEFAULT_MAX_TOOL_CALLS,
    derive_outcome,
    run_agent,
    sqlite_checkpointer,
)
from .agent.prompts import render_reply
from . import telemetry as _telemetry
from .db import connect, init_db
from .fixtures import load_fixtures
from .models import OrderItem
from .operations import (
    InsufficientStockError,
    LabelTimeoutError,
    OperationError,
    TransientError,
    WorkerCrashedError,
    create_label,
    create_return,
    escalate_case,
    finalize_arranged,
    find_exchange_stock,
    get_case,
    note_case,
    reserve_replacement,
)
from .policy import check_eligibility

MAX_ATTEMPTS = 3


def default_db_path() -> Path:
    return Path(os.environ.get("SWAPDESK_DB", "swapdesk.db"))


def ensure_db(db_path: str | Path) -> None:
    """Create schema; seed fixtures only on a fresh database."""
    conn = connect(db_path)
    try:
        init_db(conn)
        empty = conn.execute(
            "SELECT COUNT(*) AS n FROM orders").fetchone()["n"] == 0
        if empty:
            load_fixtures(conn)
    finally:
        conn.close()


def _item_record(row: sqlite3.Row) -> OrderItem:
    return OrderItem(
        id=row["id"], order_id=row["order_id"], sku=row["sku"],
        size=row["size"], qty=row["qty"], price_cents=row["price_cents"],
        status=row["status"], delivered_at=row["delivered_at"],
        final_sale=bool(row["final_sale"]), created_at=row["created_at"])


def _fetch_item(db_path, order_item_id: str):
    conn = connect(db_path)
    try:
        return conn.execute("SELECT * FROM order_items WHERE id = ?",
                            (order_item_id,)).fetchone()
    finally:
        conn.close()


def _pool(db_path, sku: str, size: str):
    conn = connect(db_path)
    try:
        return find_exchange_stock(conn, sku, size)
    finally:
        conn.close()


def _next_run_id(db_path, case_id: str) -> str:
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT DISTINCT run_id FROM operations WHERE case_id = ?",
            (case_id,)).fetchall()
    finally:
        conn.close()
    taken = {r["run_id"] for r in rows}
    n = 1
    while f"RUN-{n}" in taken:
        n += 1
    return f"RUN-{n}"


class _Exhausted(Exception):
    pass


def _attempt(log_attempts: dict, step: str, fn):
    last = None
    for n in range(1, MAX_ATTEMPTS + 1):
        log_attempts[step] = n
        try:
            return fn()
        except (TransientError, WorkerCrashedError, LabelTimeoutError,
                InsufficientStockError) as exc:
            last = exc
    raise _Exhausted(str(last))


def _escalate_none(db_path, case_id: str, reason: str) -> dict:
    note_case(db_path, case_id=case_id, state="escalated", detail=reason)
    return {"outcome": "escalation", "exchange_id": None,
            "reason": f"escalated: {reason}"}


def _escalate_held(db_path, case_id: str, run_id: str, exchange_id: str,
                   reason: str, log_attempts: dict) -> dict:
    key = f"{case_id}:{run_id}:escalate"
    last = None
    for n in range(1, MAX_ATTEMPTS + 1):
        log_attempts["escalate"] = n
        try:
            out = escalate_case(db_path, case_id=case_id, run_id=run_id,
                                op_key=key, exchange_id=exchange_id,
                                reason=reason)
            return {"outcome": "escalation",
                    "exchange_id": exchange_id,
                    "reason": f"escalated: {reason}",
                    "status": out.status}
        except (TransientError, OperationError) as exc:
            last = exc
    return {"outcome": "escalation", "exchange_id": exchange_id,
            "reason": f"escalated: {reason} (cleanup pending: {last})",
            "status": "cleanup_pending"}


def _run_flow(db_path, *, case_id: str, run_id: str, order_id: str,
              order_item_id: str, requested_size: str, qty: int,
              consent_size: str | None) -> dict:
    """Execute one run of the demo policy. Returns outcome fields."""
    log_attempts: dict = {}
    row = _fetch_item(db_path, order_item_id)
    if row is None or row["order_id"] != order_id:
        note_case(db_path, case_id=case_id, state="needs_information",
                  detail="provide your order number and item id")
        return {"outcome": "clarification", "exchange_id": None,
                "question": "provide your order number and item id",
                "attempts": log_attempts}
    item = _item_record(row)
    eligible, reason = check_eligibility(item, date.today())
    if not eligible:
        note_case(db_path, case_id=case_id, state="denied", detail=reason)
        return {"outcome": "denial", "exchange_id": None,
                "reason": f"denied: {reason}", "attempts": log_attempts}
    size = (requested_size or "").strip()
    if not size:
        note_case(db_path, case_id=case_id, state="needs_information",
                  detail="which size do you need?")
        return {"outcome": "clarification", "exchange_id": None,
                "question": "which size do you need?",
                "attempts": log_attempts}
    pool = _pool(db_path, item.sku, size)
    available = pool.available if pool else 0
    authorized = size
    if available < qty:
        consent = consent_size
        if consent:
            alt = _pool(db_path, item.sku, consent)
            if alt is not None and alt.available >= qty:
                authorized = consent
                note_case(db_path, case_id=case_id, state="received",
                          detail=f"consent:{consent}")
        if authorized == size:
            note_case(db_path, case_id=case_id, state="needs_information",
                      detail=f"size {size} unavailable")
            return {
                "outcome": "clarification", "exchange_id": None,
                "question": f"size {size} is unavailable "
                            f"(only {available} unit(s) in stock); reply "
                            "with an alternative size or ask for a human",
                "attempts": log_attempts}

    def _key(step: str) -> str:
        return f"{case_id}:{run_id}:{step}"

    try:
        res = _attempt(log_attempts, "reserve", lambda: reserve_replacement(
            db_path, case_id=case_id, run_id=run_id,
            op_key=_key("reserve"), order_id=order_id,
            order_item_id=order_item_id, size=authorized, qty=qty,
            requested_size=size, consent=authorized != size))
    except _Exhausted as exc:
        return {**_escalate_none(
            db_path, case_id, f"reservation kept failing: {exc}"),
            "attempts": log_attempts}
    except OperationError as exc:
        return {**_escalate_none(db_path, case_id, f"reservation failed: {exc}"),
                "attempts": log_attempts}
    if res.duplicate and res.status == "arranged":
        return {"outcome": "arranged", "exchange_id": res.exchange_id,
                "duplicate": True, "attempts": log_attempts}
    exchange_id = res.exchange_id

    def _do_return():
        return create_return(db_path, case_id=case_id, run_id=run_id,
                             op_key=_key("return"), exchange_id=exchange_id)

    def _do_label():
        return create_label(db_path, case_id=case_id, run_id=run_id,
                            op_key=_key("label"), exchange_id=exchange_id)

    def _do_finalize():
        return finalize_arranged(
            db_path, case_id=case_id, run_id=run_id,
            op_key=_key("finalize"), exchange_id=exchange_id)

    try:
        _attempt(log_attempts, "return", _do_return)
        _attempt(log_attempts, "label", _do_label)
        _attempt(log_attempts, "finalize", _do_finalize)
    except _Exhausted as exc:
        return {**_escalate_held(db_path, case_id, run_id, exchange_id,
                                 f"flow kept failing: {exc}", log_attempts),
                "attempts": log_attempts}
    except OperationError as exc:
        return {**_escalate_held(db_path, case_id, run_id, exchange_id,
                                 f"flow failed: {exc}", log_attempts),
                "attempts": log_attempts}
    return {"outcome": "arranged", "exchange_id": exchange_id,
            "duplicate": res.duplicate, "attempts": log_attempts}


def _telemetry_span(case_id: str, run_id: str):
    import neatlogs

    @contextlib.contextmanager
    def _span():
        with neatlogs.trace(f"swapdesk-api:{case_id}",
                             kind="WORKFLOW") as span:
            span.set_attribute("swapdesk.case_id", case_id)
            span.set_attribute("swapdesk.run_id", run_id)
            yield span

    return _span()


def _verified_reply(db_path, case_id: str) -> dict:
    ctx = AgentContext(db_path=db_path, case_id=case_id, run_id="",
                       message="")
    decided = derive_outcome(ctx)
    return {"outcome": decided["outcome"],
            "exchange_id": decided["exchange_id"],
            "reply": render_reply(decided["outcome"], decided["data"])}


def submit_ticket(db_path, *, order_id: str, order_item_id: str,
                  size: str, qty: int = 1, message: str = "",
                  consent_size: str | None = None,
                  case_id: str | None = None) -> dict:
    """Open a case and run it to a verified outcome."""
    ensure_db(db_path)
    cid = case_id or f"CASE-{uuid.uuid4().hex[:8]}"
    if get_case(db_path, cid) is not None:
        raise ValueError(f"case {cid!r} already exists")
    _telemetry.init_telemetry()
    with _telemetry_span(cid, "RUN-1"):
        result = _run_flow(db_path, case_id=cid, run_id="RUN-1",
                           order_id=order_id, order_item_id=order_item_id,
                           requested_size=size, qty=qty,
                           consent_size=consent_size)
    verified = _verified_reply(db_path, cid)
    return {"case_id": cid, "run_id": "RUN-1", **verified,
            "attempts": result.get("attempts", {})}


class AgentExecutionError(Exception):
    """Agent run failed; its checkpoint can be resumed with this identity."""

    def __init__(self, case_id: str, run_id: str):
        self.case_id = case_id
        self.run_id = run_id
        super().__init__("agent execution failed")


def submit_agent_ticket(db_path, *, message: str,
                        order_id: str | None = None,
                        order_item_id: str | None = None,
                        size: str | None = None, qty: int = 1,
                        consent_size: str | None = None,
                        case_id: str | None = None,
                        resume: bool = False,
                        run_id: str = "RUN-1",
                        model=None, middleware=(),
                        max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
                        ) -> dict:
    """Run a natural-language ticket through the checkpointed LangGraph agent.

    The single agent execution implementation: queue workers call this per
    claimed run with the run's saved request. Optional model/middleware
    exist for offline doubles and provider-request budgets; production
    uses the configured provider with no silent fallback.
    """
    ensure_db(db_path)
    cid = case_id or f"CASE-{uuid.uuid4().hex[:8]}"
    exists = get_case(db_path, cid) is not None
    if exists and not resume:
        raise ValueError(f"case {cid!r} already exists; set resume=true")

    fields = {key: value for key, value in {
        "order_id": order_id, "order_item_id": order_item_id,
        "size": size, "qty": qty,
    }.items() if value is not None}
    agent_message = message.strip()
    if not agent_message:
        raise ValueError("message must not be blank")
    if fields:
        agent_message += "\n\nStructured ticket fields: " + json.dumps(
            fields, sort_keys=True)
    ctx = AgentContext(
        db_path=db_path, case_id=cid, run_id=run_id,
        message=agent_message, consent_size=consent_size,
        order_id=order_id, order_item_id=order_item_id,
        requested_size=size, qty=qty)
    checkpoint_path = Path(f"{db_path}.agent-checkpoints.sqlite")
    try:
        with sqlite_checkpointer(checkpoint_path) as checkpointer:
            result = run_agent(ctx, model=model, checkpointer=checkpointer,
                               max_tool_calls=max_tool_calls,
                               middleware=middleware)
    except ConfigurationError:
        raise
    except Exception as exc:
        raise AgentExecutionError(cid, run_id) from exc
    return {"case_id": cid, "run_id": run_id,
            "outcome": result["outcome"], "reply": result["reply"],
            "exchange_id": result["exchange_id"], "resumed": resume}


def continue_case(db_path, *, case_id: str, message: str = "",
                  consent_size: str | None = None,
                  order_id: str | None = None,
                  order_item_id: str | None = None,
                  size: str | None = None, qty: int = 1) -> dict:
    """Continue a case with new customer input.

    Terminal cases report their verified status unchanged. Otherwise the
    request runs again under a fresh run id (duplicate-safe). The request
    comes from explicit fields when given, else from the case's latest
    exchange row; without either, continuation is a client error.
    """
    ensure_db(db_path)
    current = _verified_reply(db_path, case_id)
    if current["outcome"] in ("arranged", "denial"):
        return {"case_id": case_id, "run_id": None, **current,
                "attempts": {}, "continued": False}
    run_id = _next_run_id(db_path, case_id)
    if order_id is not None and order_item_id is not None and size is not None:
        request = {"order_id": order_id, "order_item_id": order_item_id,
                   "requested_size": size, "qty": qty}
    else:
        conn = connect(db_path)
        try:
            anchor = conn.execute(
                "SELECT order_id, order_item_id, requested_size, qty "
                "FROM exchanges WHERE case_id = ? "
                "ORDER BY rowid DESC LIMIT 1", (case_id,)).fetchone()
        finally:
            conn.close()
        if anchor is None:
            raise ValueError(
                f"case {case_id!r} has no recorded request to continue; "
                "provide order_id, order_item_id and size")
        request = dict(anchor)
    _ = message
    _telemetry.init_telemetry()
    with _telemetry_span(case_id, run_id):
        result = _run_flow(db_path, case_id=case_id, run_id=run_id,
                           consent_size=consent_size, **request)
    verified = _verified_reply(db_path, case_id)
    return {"case_id": case_id, "run_id": run_id, **verified,
            "attempts": result.get("attempts", {}), "continued": True}


def case_status(db_path, case_id: str) -> dict | None:
    """Verified status of a case, or None when unknown."""
    ensure_db(db_path)
    if get_case(db_path, case_id) is None:
        return None
    conn = connect(db_path)
    try:
        runs = [r["run_id"] for r in conn.execute(
            "SELECT DISTINCT run_id FROM operations WHERE case_id = ?",
            (case_id,))]
    finally:
        conn.close()
    return {"case_id": case_id, **_verified_reply(db_path, case_id),
            "runs": sorted(runs)}


def case_timeline(db_path, case_id: str) -> list[dict] | None:
    """Sanitized run/action timeline: journal plus operation records."""
    ensure_db(db_path)
    if get_case(db_path, case_id) is None:
        return None
    conn = connect(db_path)
    try:
        ops = {r["idempotency_key"]: dict(r) for r in conn.execute(
            "SELECT * FROM operations WHERE case_id = ? ORDER BY rowid",
            (case_id,))}
        events = []
        for row in conn.execute(
                "SELECT * FROM journal WHERE op_key IN "
                "(SELECT idempotency_key FROM operations WHERE case_id = ?) "
                "ORDER BY rowid", (case_id,)):
            op = ops.get(row["op_key"], {})
            events.append({
                "op_key": row["op_key"],
                "op_type": op.get("op_type"),
                "event": row["event"],
                "status": op.get("status"),
                "result": (json.loads(op["result_json"])
                           if op.get("result_json") else None),
                "created_at": row["created_at"],
            })
    finally:
        conn.close()
    return events


def fixture_catalog(db_path) -> dict:
    """Synthetic fixture choices for frontend dropdowns, plus policy."""
    from .operations import get_return_policy

    ensure_db(db_path)
    conn = connect(db_path)
    try:
        orders = []
        for order in conn.execute("SELECT * FROM orders ORDER BY id"):
            items = [dict(r) for r in conn.execute(
                "SELECT id, sku, size, qty, status, delivered_at, "
                "final_sale FROM order_items WHERE order_id = ? ORDER BY id",
                (order["id"],))]
            orders.append({"id": order["id"],
                           "customer_ref": order["customer_ref"],
                           "items": items})
    finally:
        conn.close()
    return {"orders": orders, "policy": get_return_policy()}


def arm_demo_fault(*, case_id: str, run_id: str, step: str, point: str,
                   times: int = 1) -> dict:
    """Demo-only failure control: arm a fault on one operation key."""
    _faults.inject(f"{case_id}:{run_id}:{step}", point, times)
    return {"armed": True, "op_key": f"{case_id}:{run_id}:{step}",
            "point": point, "times": times}


def clear_demo_faults() -> dict:
    """Demo-only failure control: disarm every fault."""
    _faults.clear()
    return {"cleared": True}
