"""Deterministic reference driver. NOT the agent.

Follows one fixed, documented policy so the checker has real executions
to verify against the frozen cases. The Slice 4 agent will face the same
cases without ever seeing expected answers.

Policy: unknown/mismatched item -> clarification; ineligible -> denial;
missing size -> clarification; insufficient stock -> consented alternative
or clarification; faults -> bounded retries on the SAME key (re-query
status after crash/timeout); exhausted retries or abandonment ->
escalation with release. Replies are fixed templates (a preview of the
Slice 4 verified-template rule), never model prose.
"""

from __future__ import annotations

from datetime import date

from swapdesk import (
    InsufficientStockError,
    LabelTimeoutError,
    OperationError,
    ReleaseFailedError,
    TransientError,
    WorkerCrashedError,
    cancel_exchange,
    create_label,
    create_return,
    escalate_case,
    finalize_arranged,
    find_exchange_stock,
    note_case,
    reserve_replacement,
)
from swapdesk.db import connect
from swapdesk.models import OrderItem
from swapdesk.policy import check_eligibility

MAX_ATTEMPTS = 3


def _record(row) -> OrderItem:
    return OrderItem(
        id=row["id"], order_id=row["order_id"], sku=row["sku"],
        size=row["size"], qty=row["qty"], price_cents=row["price_cents"],
        status=row["status"], delivered_at=row["delivered_at"],
        final_sale=bool(row["final_sale"]), created_at=row["created_at"],
    )


def _pool(db_path, sku: str, size: str):
    conn = connect(db_path)
    try:
        return find_exchange_stock(conn, sku, size)
    finally:
        conn.close()


class _Exhausted(Exception):
    pass


def _key(case_id: str, run_tag: str, step: str) -> str:
    return f"{case_id}:{run_tag}:{step}"


def _deny(db_path, case_id: str, reason: str) -> dict:
    note_case(db_path, case_id=case_id, state="denied", detail=reason)
    return {"case_id": case_id, "outcome": "denied", "exchange_id": None,
            "status": None, "reason": f"denied: {reason}", "question": None,
            "duplicate": False, "attempts": {}}


def _clarify(db_path, case_id: str, question: str) -> dict:
    note_case(db_path, case_id=case_id, state="needs_information",
              detail=question)
    return {"case_id": case_id, "outcome": "clarification",
            "exchange_id": None, "status": None, "reason": None,
            "question": f"clarification: {question}", "duplicate": False,
            "attempts": {}}


def _attempt(log: dict, step: str, fn):
    """Bounded retries on the same key. Crash/timeout recover via saved."""
    last = None
    for n in range(1, MAX_ATTEMPTS + 1):
        log["attempts"][step] = n
        try:
            return fn()
        except (TransientError, WorkerCrashedError, LabelTimeoutError,
                InsufficientStockError) as exc:
            last = exc
    raise _Exhausted(str(last))


def _escalate_none(db_path, case_id: str, reason: str) -> dict:
    note_case(db_path, case_id=case_id, state="escalated", detail=reason)
    return {"case_id": case_id, "outcome": "escalated", "exchange_id": None,
            "status": None, "reason": f"escalated: {reason}",
            "question": None, "duplicate": False, "attempts": {}}


def _escalate_held(db_path, case_id: str, run_id: str, op_key: str,
                   exchange_id: str, reason: str, log: dict) -> dict:
    last = None
    for n in range(1, MAX_ATTEMPTS + 1):
        log["attempts"]["escalate"] = n
        try:
            out = escalate_case(db_path, case_id=case_id, run_id=run_id,
                                op_key=op_key, exchange_id=exchange_id,
                                reason=reason)
            return {"case_id": case_id, "outcome": "escalated",
                    "exchange_id": exchange_id, "status": out.status,
                    "reason": f"escalated: {reason}", "question": None,
                    "duplicate": out.duplicate, "attempts": log["attempts"]}
        except (ReleaseFailedError, TransientError) as exc:
            last = exc
    return {"case_id": case_id, "outcome": "escalated",
            "exchange_id": exchange_id, "status": "cleanup_pending",
            "reason": f"escalated: {reason} (cleanup pending: {last})",
            "question": None, "duplicate": False, "attempts": log["attempts"]}


def _fetch_item(db_path, order_item_id: str):
    conn = connect(db_path)
    try:
        return conn.execute("SELECT * FROM order_items WHERE id = ?",
                            (order_item_id,)).fetchone()
    finally:
        conn.close()


def _run_standard(db_path, case: dict, run_tag: str = "r1",
                  case_id: str | None = None) -> dict:
    cid = case_id or case["case_id"]
    run_id = case.get("run_id", f"{cid}-RUN-{run_tag}")
    log: dict = {"case_id": cid, "outcome": None, "exchange_id": None,
                 "status": None, "reason": None, "question": None,
                 "duplicate": False, "attempts": {}}
    qty = case.get("qty", 1)

    row = _fetch_item(db_path, case["order_item_id"])
    if row is None:
        return _clarify(db_path, cid,
                        "provide your order number and item id")
    if row["order_id"] != case["order_id"]:
        return _clarify(
            db_path, cid,
            f"item {case['order_item_id']} is not on order "
            f"{case['order_id']}; check both and reply")
    item = dict(row)
    eligible, reason = check_eligibility(_record(row), date.today())
    if not eligible:
        return _deny(db_path, cid, reason)

    size = (case.get("requested_size") or "").strip()
    if not size:
        return _clarify(db_path, cid, "which size do you need?")
    pool = _pool(db_path, item["sku"], size)
    available = pool.available if pool else 0
    authorized = size
    if available < qty:
        consent = case.get("consent_size")
        if consent:
            alt = _pool(db_path, item["sku"], consent)
            if alt is not None and alt.available >= qty:
                authorized = consent
                note_case(db_path, case_id=cid, state="received",
                          detail=f"consent:{consent}")
        if authorized == size:
            return _clarify(
                db_path, cid,
                f"size {size} is unavailable (only {available} unit(s) in "
                "stock); reply with an alternative size or ask for a human")

    def do_reserve():
        return reserve_replacement(
            db_path, case_id=cid, run_id=run_id,
            op_key=_key(cid, run_tag, "reserve"),
            order_id=case["order_id"], order_item_id=case["order_item_id"],
            size=authorized, qty=qty, requested_size=size)

    try:
        res = _attempt(log, "reserve", do_reserve)
    except _Exhausted as exc:
        return _escalate_none(db_path, cid, f"reservation kept failing: {exc}")
    except OperationError as exc:
        return _escalate_none(db_path, cid, f"reservation failed: {exc}")
    if res.duplicate and res.status == "arranged":
        log.update(outcome="arranged", exchange_id=res.exchange_id,
                   status="arranged", duplicate=True)
        return log
    exchange_id = res.exchange_id
    log["duplicate"] = res.duplicate

    if case.get("abandon_after") == "reserved":
        return _escalate_held(db_path, cid, run_id,
                              _key(cid, run_tag, "escalate"), exchange_id,
                              "customer abandonment", log)

    def do_return():
        return create_return(db_path, case_id=cid, run_id=run_id,
                             op_key=_key(cid, run_tag, "return"),
                             exchange_id=exchange_id)

    def do_label():
        return create_label(db_path, case_id=cid, run_id=run_id,
                            op_key=_key(cid, run_tag, "label"),
                            exchange_id=exchange_id)

    def do_finalize():
        return finalize_arranged(db_path, case_id=cid, run_id=run_id,
                                 op_key=_key(cid, run_tag, "finalize"),
                                 exchange_id=exchange_id)

    try:
        _attempt(log, "return", do_return)
        if case.get("abandon_after") == "return_created":
            return _escalate_held(db_path, cid, run_id,
                                  _key(cid, run_tag, "escalate"), exchange_id,
                                  "customer abandonment", log)
        _attempt(log, "label", do_label)
        if case.get("abandon_after") == "label_created":
            return _escalate_held(db_path, cid, run_id,
                                  _key(cid, run_tag, "escalate"), exchange_id,
                                  "customer abandonment", log)
        _attempt(log, "finalize", do_finalize)
    except _Exhausted as exc:
        return _escalate_held(db_path, cid, run_id,
                              _key(cid, run_tag, "escalate"), exchange_id,
                              f"flow kept failing: {exc}", log)
    except OperationError as exc:
        return _escalate_held(db_path, cid, run_id,
                              _key(cid, run_tag, "escalate"), exchange_id,
                              f"flow failed: {exc}", log)
    log.update(outcome="arranged", exchange_id=exchange_id,
               status="arranged")
    return log


def run_case(db_path, case: dict, run_tag: str = "r1") -> dict:
    """Run one frozen case by script name. Scripts share one database."""
    script = case.get("script", "standard")
    if script == "standard":
        if case.get("split_runs"):
            return _run_split(db_path, case, run_tag)
        return _run_standard(db_path, case, run_tag)
    if script == "rerun":
        first = _run_standard(db_path, case, "r1")
        second = _run_standard(db_path, case, "r2")
        first["second"] = second
        first["duplicate"] = second.get("duplicate", False)
        first["status"] = second.get("status", first.get("status"))
        return first
    if script == "cross_case":
        first = _run_standard(db_path, case, "r1")
        second_case = dict(case["second_case"])
        second = _run_standard(db_path, second_case, "r1",
                               case_id=second_case["case_id"])
        first["second"] = second
        first["duplicate"] = second.get("duplicate", False)
        return first
    if script == "cancel_fresh":
        first = _run_standard(db_path, case, "r1")
        cancel_exchange(db_path, case_id=case["case_id"],
                        run_id=f"{case['case_id']}-RUN-r1x",
                        op_key=f"{case['case_id']}:r1x:cancel",
                        exchange_id=first["exchange_id"],
                        reason="customer changed mind, retrying fresh")
        second = _run_standard(db_path, case, "r2")
        second["first_exchange"] = first["exchange_id"]
        return second
    raise ValueError(f"unknown script {script!r}")


def _run_split(db_path, case: dict, run_tag: str) -> dict:
    """Reserve under RUN-1, finish under RUN-2: progress spans runs."""
    cid = case["case_id"]
    res = reserve_replacement(
        db_path, case_id=cid, run_id=f"{cid}-RUN-1",
        op_key=_key(cid, run_tag, "reserve"), order_id=case["order_id"],
        order_item_id=case["order_item_id"], size=case["requested_size"],
        qty=case.get("qty", 1))
    create_return(db_path, case_id=cid, run_id=f"{cid}-RUN-2",
                  op_key=_key(cid, run_tag, "return"),
                  exchange_id=res.exchange_id)
    create_label(db_path, case_id=cid, run_id=f"{cid}-RUN-2",
                 op_key=_key(cid, run_tag, "label"),
                 exchange_id=res.exchange_id)
    finalize_arranged(db_path, case_id=cid, run_id=f"{cid}-RUN-2",
                      op_key=_key(cid, run_tag, "finalize"),
                      exchange_id=res.exchange_id)
    return {"case_id": cid, "outcome": "arranged",
            "exchange_id": res.exchange_id, "status": "arranged",
            "reason": None, "question": None, "duplicate": False,
            "attempts": {"reserve": 1, "return": 1, "label": 1,
                         "finalize": 1}}
