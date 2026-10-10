"""Deterministic benchmark checker. No LLM judge, no agent imports.

check_run() re-derives everything from the database plus a pre-run
baseline snapshot: expected outcome per case, global invariants
(nonnegative inventory, hold reconciliation, journal linkage, no
unrelated record changes), and run-log truthfulness (the driver must
not claim what the database does not show).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date
import json as _json

from .db import connect
from .operations import verify_exchange
from .policy import check_eligibility


@dataclass
class CheckResult:
    case_id: str
    repeat: int
    passed: bool
    failures: list[str] = field(default_factory=list)


def _failures() -> list[str]:
    return []


def _rows(conn: sqlite3.Connection, table: str) -> list[dict]:
    return [dict(r) for r in conn.execute(f"SELECT * FROM {table}")]


def _snapshot(conn: sqlite3.Connection) -> dict:
    return {
        "orders": _rows(conn, "orders"),
        "order_items": _rows(conn, "order_items"),
        "stock": _rows(conn, "stock"),
    }


def check_run(db_path, case: dict, run_log: dict, baseline: dict,
              repeat: int = 1) -> CheckResult:
    """Verify one case execution. Returns pass/fail with reasons."""
    failures = _failures()
    case_id = case["case_id"]
    outcome = case["outcome"]

    conn = connect(db_path)
    try:
        after = _snapshot(conn)
        exchanges = _rows(conn, "exchanges")
        returns = _rows(conn, "returns")
        labels = _rows(conn, "labels")
        operations = _rows(conn, "operations")
        journal = _rows(conn, "journal")
        cases = {}
        for r in _rows(conn, "cases"):
            row = dict(r)
            row["progress"] = _json.loads(row.pop("progress_json"))
            cases[row["case_id"]] = row
    finally:
        conn.close()

    item_id = case["order_item_id"]
    item_exchanges = [e for e in exchanges if e["order_item_id"] == item_id]
    case_ops = [o for o in operations
                if o["case_id"] in _involved_cases(case, run_log)]

    _check_invariants(case, baseline, after, exchanges, operations, journal,
                      failures)
    _check_log_truthfulness(case, run_log, item_exchanges, failures)

    if outcome == "arranged":
        _check_arranged(db_path, case, run_log, item_exchanges, returns,
                        labels, case_ops, cases, baseline, after, failures)
    elif outcome in ("denied", "clarification"):
        _check_no_writes(case, run_log, item_exchanges, returns, labels,
                         case_ops, baseline, after, failures)
        _check_case_state(case, cases, failures)
        _check_message(case, run_log, failures)
    elif outcome == "escalated":
        _check_escalated(db_path, case, run_log, item_exchanges, returns,
                         labels, case_ops, cases, failures)
    else:
        failures.append(f"unknown expected outcome {outcome!r}")

    return CheckResult(case_id=case_id, repeat=repeat,
                       passed=not failures, failures=failures)


def _involved_cases(case: dict, run_log: dict) -> set[str]:
    ids = {case["case_id"]}
    second = run_log.get("second") or {}
    if second.get("case_id"):
        ids.add(second["case_id"])
    return ids


def _check_invariants(case, baseline, after, exchanges, operations, journal,
                      failures) -> None:
    # Orders and items are reference data: never change.
    if after["orders"] != baseline["orders"]:
        failures.append("orders table changed during the run")
    if after["order_items"] != baseline["order_items"]:
        failures.append("order_items table changed during the run")
    # Nonnegative inventory everywhere.
    for row in after["stock"]:
        if row["held"] < 0 or row["on_hand"] < 0:
            failures.append(
                f"negative stock at {row['sku']}/{row['size']}")
        if row["on_hand"] - row["held"] < 0:
            failures.append(
                f"oversold pool {row['sku']}/{row['size']}")
    # Hold reconciliation: every outstanding hold is backed by an exchange.
    held_total = sum(r["held"] for r in after["stock"])
    base_held = sum(r["held"] for r in baseline["stock"])
    open_holds = sum(
        e["qty"] for e in exchanges
        if not e["hold_released"] and e["status"] in (
            "replacement_reserved", "return_created", "label_created",
            "cleanup_pending"))
    if held_total != base_held + open_holds:
        failures.append(
            f"orphan holds: stock held={held_total} but open exchange "
            f"holds={open_holds} (baseline {base_held})")
    # Journal linkage: every recorded op key left at least one event.
    journaled = {j["op_key"] for j in journal}
    for op in operations:
        if op["idempotency_key"] not in journaled:
            failures.append(
                f"op {op['idempotency_key']!r} has no journal event")
    # Only the case's own pools may move.
    allowed_pools = {(case.get("sku"), case.get("requested_size")),
                     (case.get("sku"), case.get("consent_size"))}
    before_pools = {(r["sku"], r["size"]): (r["on_hand"], r["held"])
                    for r in baseline["stock"]}
    after_pools = {(r["sku"], r["size"]): (r["on_hand"], r["held"])
                   for r in after["stock"]}
    for pool, vals in after_pools.items():
        if vals != before_pools.get(pool) and pool not in allowed_pools:
            failures.append(f"unrelated stock pool changed: {pool}")


def _check_log_truthfulness(case, run_log, item_exchanges, failures) -> None:
    claimed = run_log.get("exchange_id")
    if claimed is None:
        return
    match = [e for e in item_exchanges if e["id"] == claimed]
    if not match:
        failures.append(
            f"run log claims exchange {claimed!r} but it is not in the db")
        return
    if run_log.get("status") and run_log["status"] != match[0]["status"]:
        failures.append(
            f"run log claims status {run_log['status']!r} but db has "
            f"{match[0]['status']!r}")


def _expected_size(case) -> str:
    return case["consent_size"] or case["requested_size"]


def _check_arranged(db_path, case, run_log, item_exchanges, returns,
                    labels, case_ops, cases, baseline, after, failures) -> None:
    exp_size = _expected_size(case)
    arranged = [e for e in item_exchanges if e["status"] == "arranged"]
    cancelled = [e for e in item_exchanges if e["status"] == "cancelled"]
    others = [e for e in item_exchanges
              if e["status"] not in ("arranged", "cancelled")]
    if len(arranged) != 1:
        failures.append(
            f"expected exactly 1 arranged exchange, found {len(arranged)}")
        return
    if others:
        failures.append(
            f"unexpected exchange states: {[e['status'] for e in others]}")
    if len(cancelled) > 1:
        failures.append("more than one cancelled exchange for one item")
    winner = arranged[0]
    items = {i["id"]: i for i in after["order_items"]}
    item = items.get(winner["order_item_id"])
    if item is None:
        failures.append("arranged exchange references a missing item")
        return
    eligible, _ = check_eligibility(_item_record(item), date.today())
    if not eligible:
        failures.append("arranged exchange is not eligible")
    if winner["authorized_size"] != exp_size or winner["qty"] != case["qty"]:
        failures.append(
            f"wrong size/qty: {winner['authorized_size']}/{winner['qty']}, "
            f"expected {exp_size}/{case['qty']}")
    if case["consent_size"] and winner["requested_size"] == exp_size:
        failures.append("consent case must authorize a different size")
    if case.get("consent_size"):
        notes = cases.get(case["case_id"], {}).get("progress", {}).get(
            "notes", [])
        if not any(f"consent:{case['consent_size']}" in n.get("detail", "")
                   for n in notes):
            failures.append("consented size has no recorded consent note")
    # One committed effect per step, no second committed effects.
    for op_type, want in (("reserve_replacement", 1), ("create_return", 1),
                          ("create_label", 1), ("finalize_arranged", 1)):
        got = [o for o in case_ops
               if o["op_type"] == op_type and o["status"] == "committed"
               and _op_exchange(o) in ({winner["id"]}
                                       | {c["id"] for c in cancelled})]
        if len(got) != want and not (cancelled and op_type == "reserve_replacement" and len(got) == 2):
            failures.append(
                f"expected {want} committed {op_type}, found {len(got)}")
    if len([r for r in returns if r["exchange_id"] == winner["id"]]) != 1:
        failures.append("expected exactly 1 return row for the exchange")
    if len([label for label in labels
            if label["exchange_id"] == winner["id"]]) != 1:
        failures.append("expected exactly 1 label row for the exchange")
    # Truthful status via the read-only handoff.
    handoff = verify_exchange(db_path, winner["id"])
    if not handoff.consistent or handoff.status != "arranged":
        failures.append("handoff inconsistent with an arranged exchange")
    if run_log.get("exchange_id") != winner["id"]:
        failures.append("run log names the wrong exchange")
    # Stock consumed exactly once per arranged exchange touching each pool.
    before_pools = {(r["sku"], r["size"]): (r["on_hand"], r["held"])
                    for r in baseline["stock"]}
    after_pools = {(r["sku"], r["size"]): (r["on_hand"], r["held"])
                   for r in after["stock"]}
    consumed: dict[tuple, int] = {}
    for e in arranged:
        pool = (item["sku"], e["authorized_size"])
        consumed[pool] = consumed.get(pool, 0) + e["qty"]
    for pool, qty in consumed.items():
        base = before_pools.get(pool)
        now = after_pools.get(pool)
        if base is None or now is None:
            failures.append(f"arranged pool {pool} missing from stock")
            continue
        if now != (base[0] - qty, base[1]):
            failures.append(
                f"pool {pool} is {now}, expected {(base[0] - qty, base[1])}")
    state = cases.get(case["case_id"], {}).get("state")
    if state != "arranged":
        failures.append(f"case state is {state!r}, expected 'arranged'")
    if case.get("expect_duplicate") and not run_log.get("duplicate"):
        failures.append("expected the repeat run to report duplicate reuse")


def _op_exchange(op: dict) -> str:
    import json as _json
    result = _json.loads(op["result_json"])
    return result.get("exchange_id", "")


def _item_record(row: dict):
    from .models import OrderItem
    return OrderItem(
        id=row["id"], order_id=row["order_id"], sku=row["sku"],
        size=row["size"], qty=row["qty"], price_cents=row["price_cents"],
        status=row["status"], delivered_at=row["delivered_at"],
        final_sale=bool(row["final_sale"]), created_at=row["created_at"],
    )


def _check_no_writes(case, run_log, item_exchanges, returns, labels,
                     case_ops, baseline, after, failures) -> None:
    mine = [e["id"] for e in item_exchanges]
    if mine:
        failures.append(f"expected no exchange writes, found {mine}")
    mine_returns = [r["id"] for r in returns
                    if r["exchange_id"] in set(mine)]
    mine_labels = [label["id"] for label in labels
                   if label["exchange_id"] in set(mine)]
    if mine_returns or mine_labels:
        failures.append("expected no return/label writes")
    if case_ops:
        failures.append(
            f"expected no operation rows, found "
            f"{[o['idempotency_key'] for o in case_ops]}")
    before_pools = {(r["sku"], r["size"]): (r["on_hand"], r["held"])
                    for r in baseline["stock"]}
    after_pools = {(r["sku"], r["size"]): (r["on_hand"], r["held"])
                   for r in after["stock"]}
    if before_pools != after_pools:
        failures.append("expected inventory completely unchanged")


def _check_case_state(case, cases, failures) -> None:
    want = {"denied": "denied", "clarification": "needs_information"}[
        case["outcome"]]
    got = cases.get(case["case_id"], {}).get("state")
    if got != want:
        failures.append(f"case state is {got!r}, expected {want!r}")


def _check_message(case, run_log, failures) -> None:
    if case["outcome"] == "denied":
        needle = case.get("reason_contains", "")
        hay = run_log.get("reason", "")
    else:
        needle = case.get("question_contains", "")
        hay = run_log.get("question", "")
    if needle and needle not in hay:
        failures.append(
            f"expected message containing {needle!r}, got {hay!r}")


def _check_escalated(db_path, case, run_log, item_exchanges, returns,
                     labels, case_ops, cases, failures) -> None:
    needle = case.get("reason_contains", "")
    if needle and needle not in run_log.get("reason", ""):
        failures.append(
            f"expected escalation reason {needle!r}, "
            f"got {run_log.get('reason', '')!r}")
    cleaning = case.get("expect_cleanup", "done")
    claimed = run_log.get("exchange_id")
    if cleaning == "none":
        if item_exchanges:
            failures.append("expected no exchange rows for a clean escalation")
        if case_ops:
            failures.append("expected no operation rows for a clean escalation")
    else:
        match = [e for e in item_exchanges if e["id"] == claimed]
        if not match:
            failures.append("escalation names no persisted exchange")
            return
        hand = verify_exchange(db_path, claimed)
        if not hand.consistent:
            failures.append("partial-state handoff is inconsistent")
        if bool([r for r in returns if r["exchange_id"] == claimed]) != bool(
                case.get("expect_return_row")):
            failures.append("return-row history does not match expectation")
        if bool([label for label in labels
                 if label["exchange_id"] == claimed]) != bool(
                case.get("expect_label_row")):
            failures.append("label-row history does not match expectation")
        if cleaning == "done":
            if hand.status != "escalated" or hand.hold_active:
                failures.append(
                    f"expected released escalated handoff, got "
                    f"{hand.status} hold_active={hand.hold_active}")
        else:
            if hand.status != "cleanup_pending" or not hand.pending_cleanup:
                failures.append(
                    f"expected visible cleanup_pending, got {hand.status}")
            failed = [o for o in case_ops if o["status"] == "failed"]
            if not failed:
                failures.append("expected an explicit failed cleanup record")
    state = cases.get(case["case_id"], {}).get("state")
    want_states = {"done": ("escalated",), "pending": ("cleanup_pending",),
                   "none": ("escalated",)}[cleaning]
    if state not in want_states:
        failures.append(f"case state is {state!r}, expected one of {want_states}")
