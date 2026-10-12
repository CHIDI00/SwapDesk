"""Durable work queue for the customer agent path. One concern only.

POST /v1/agent/tickets persists the accepted request here and returns
202; a single worker claims queued runs atomically and executes them
through service.submit_agent_ticket (the one agent execution
implementation). Status/timeline reads never block on the worker: short
connections, WAL, IMMEDIATE only on writes.

Interrupted `running` rows are marked `failed` on worker startup and are
never replayed blindly; an explicit continue starts a fresh RUN-n with
preserved consent and fresh action keys. Paid executions are never
retried automatically.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from pathlib import Path

from . import db as _db
from .agent.model_spans import sanitize as _sanitize
from .db import connect
from .models import payload_hash

QUEUE_SCHEMA = """
CREATE TABLE IF NOT EXISTS submissions (
  idempotency_key TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
  case_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  thread_id TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL,
  request_json TEXT NOT NULL,
  outcome TEXT,
  reply TEXT,
  exchange_id TEXT,
  error TEXT,
  trace_id TEXT,
  requests_spent INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (case_id, run_id)
);
CREATE INDEX IF NOT EXISTS ix_runs_state ON runs(state, created_at);
"""

TERMINAL_OUTCOMES = frozenset({"arranged", "denial", "escalation"})

_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}")


class SubmissionConflict(Exception):
    """Same submission key with a different payload."""


class ConcurrentRun(Exception):
    """Case already has a queued or running run."""


def default_db_path() -> Path:
    return Path(os.environ.get("SWAPDESK_DB", "swapdesk.db"))


def ensure_queue_schema(db_path: str | Path) -> None:
    from .service import ensure_db

    ensure_db(db_path)
    conn = connect(db_path)
    try:
        conn.executescript(QUEUE_SCHEMA)
        # Migration for databases created before requests_spent existed.
        try:
            conn.execute("ALTER TABLE runs ADD COLUMN requests_spent INTEGER")
        except Exception:
            pass
    finally:
        conn.close()


def _check_id(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ValueError(
            f"{label} must use 1-96 letters, digits, underscores or hyphens")
    return value


def _new_case_id() -> str:
    return f"CASE-{uuid.uuid4().hex[:8]}"


def _new_thread_id(case_id: str, run_id: str) -> str:
    # Globally unique, scoped to the case; mirrors the agent checkpoint
    # thread f"{case_id}:{run_id}" with a unique suffix per queue run.
    return f"{case_id}:{run_id}:{uuid.uuid4().hex[:8]}"


def _canonical_request(*, message: str, order_id, order_item_id,
                       size, qty, consent_size) -> dict:
    return {
        "message": message,
        "order_id": order_id,
        "order_item_id": order_item_id,
        "size": size,
        "qty": qty,
        "consent_size": consent_size,
    }


def _next_run_id(runs: list[str]) -> str:
    taken = set(runs)
    n = 1
    while f"RUN-{n}" in taken:
        n += 1
    return f"RUN-{n}"


def submit_agent_request(db_path, *, message: str,
                         order_id: str | None = None,
                         order_item_id: str | None = None,
                         size: str | None = None,
                         qty: int = 1,
                         consent_size: str | None = None,
                         case_id: str | None = None,
                         idempotency_key: str | None = None) -> dict:
    """Persist an agent-ticket request and queue RUN-1. Returns accept fields."""
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message must not be blank")
    if not isinstance(qty, int) or qty < 1:
        raise ValueError("qty must be at least 1")
    case_id = _check_id(case_id, "case_id")
    idempotency_key = _check_id(idempotency_key, "idempotency_key")
    ensure_queue_schema(db_path)
    payload = _canonical_request(
        message=message.strip(), order_id=order_id,
        order_item_id=order_item_id, size=size, qty=qty,
        consent_size=consent_size)
    digest = payload_hash(payload)
    key = idempotency_key or case_id

    conn = connect(db_path)
    try:
        with _db.immediate(conn):
            if key is not None:
                saved = conn.execute(
                    "SELECT * FROM submissions WHERE idempotency_key = ?",
                    (key,)).fetchone()
                if saved is not None:
                    if saved["payload_hash"] != digest:
                        raise SubmissionConflict(
                            f"submission key {key!r} was already used "
                            "with a different payload")
                    existing = saved["case_id"]
                    first = conn.execute(
                        "SELECT run_id FROM runs WHERE case_id = ? "
                        "ORDER BY rowid LIMIT 1", (existing,)).fetchone()
                    return {"case_id": existing,
                            "run_id": first["run_id"] if first else "RUN-1",
                            "execution_status": _case_execution(conn,
                                                               existing),
                            "duplicate": True}
            cid = case_id or _new_case_id()
            existing_runs = [r["run_id"] for r in conn.execute(
                "SELECT run_id FROM runs WHERE case_id = ?", (cid,))]
            if existing_runs:
                # Explicit case_id reuse never starts a new exchange.
                first = conn.execute(
                    "SELECT run_id FROM runs WHERE case_id = ? "
                    "ORDER BY rowid LIMIT 1", (cid,)).fetchone()
                if key is not None:
                    conn.execute(
                        "INSERT OR IGNORE INTO submissions "
                        "(idempotency_key, case_id, payload_hash, "
                        "payload_json, created_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (key, cid, digest,
                         json.dumps(payload, sort_keys=True), _db.utcnow()))
                return {"case_id": cid, "run_id": first["run_id"],
                        "execution_status": _case_execution(conn, cid),
                        "duplicate": True}
            run_id = "RUN-1"
            now = _db.utcnow()
            conn.execute(
                "INSERT INTO runs (case_id, run_id, thread_id, state, "
                "request_json, created_at, updated_at) "
                "VALUES (?, ?, ?, 'queued', ?, ?, ?)",
                (cid, run_id, _new_thread_id(cid, run_id),
                 json.dumps(payload, sort_keys=True), now, now))
            if key is not None:
                conn.execute(
                    "INSERT INTO submissions (idempotency_key, case_id, "
                    "payload_hash, payload_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (key, cid, digest,
                     json.dumps(payload, sort_keys=True), now))
            return {"case_id": cid, "run_id": run_id,
                    "execution_status": "queued", "duplicate": False}
    finally:
        conn.close()


def _case_execution(conn, case_id: str) -> str:
    rows = conn.execute(
        "SELECT run_id, state, outcome FROM runs WHERE case_id = ? "
        "ORDER BY rowid", (case_id,)).fetchall()
    if not rows:
        return "queued"
    states = [r["state"] for r in rows]
    if "running" in states:
        return "running"
    if "queued" in states:
        return "queued"
    last = rows[-1]
    if last["state"] == "failed":
        return "failed"
    if last["outcome"] == "clarification":
        return "waiting_input"
    return "completed"


def _latest_request(conn, case_id: str) -> dict:
    row = conn.execute(
        "SELECT request_json FROM runs WHERE case_id = ? ORDER BY rowid DESC "
        "LIMIT 1", (case_id,)).fetchone()
    return json.loads(row["request_json"]) if row else {}


def continue_agent_request(db_path, case_id: str, *, message: str = "",
                           consent_size: str | None = None,
                           order_id: str | None = None,
                           order_item_id: str | None = None,
                           size: str | None = None,
                           qty: int = 1) -> dict | None:
    """Queue a continuation run through the same agent path.

    Returns None when the case is unknown to the queue. Terminal cases
    return their saved result with continued=False and no model call.
    """
    from . import service as _service

    ensure_queue_schema(db_path)
    conn = connect(db_path)
    try:
        with _db.immediate(conn):
            runs = conn.execute(
                "SELECT run_id, state, outcome FROM runs WHERE case_id = ? "
                "ORDER BY rowid", (case_id,)).fetchall()
            if not runs:
                return None
            states = [r["state"] for r in runs]
            if "running" in states or "queued" in states:
                raise ConcurrentRun(
                    f"case {case_id!r} already has a queued or running run")
            if runs[-1]["state"] == "completed" \
                    and runs[-1]["outcome"] in TERMINAL_OUTCOMES:
                current = _public_status(db_path, conn, case_id)
                return {**current, "continued": False}
            has_input = bool((message or "").strip()) \
                or consent_size is not None \
                or order_id is not None or order_item_id is not None \
                or size is not None
            if not has_input:
                raise ValueError(
                    "continue requires a message, consent_size, or "
                    "explicit order fields")
            if not isinstance(qty, int) or qty < 1:
                raise ValueError("qty must be at least 1")
            base = _latest_request(conn, case_id)
            reply = (message or "").strip()
            prior = base.get("message", "")
            # Keep the whole conversation in the run input: each reply
            # appends to the stored thread instead of replacing it, so
            # the agent sees answered questions and stops re-asking.
            # Always append: skipping "already seen" replies once
            # discarded the original complaint on identical repeats.
            thread = (prior + "\n\nCustomer reply: " + reply).strip() \
                if reply and prior \
                else (reply or prior)
            effective = {
                "message": thread,
                "order_id": order_id if order_id is not None
                else base.get("order_id"),
                "order_item_id": order_item_id if order_item_id is not None
                else base.get("order_item_id"),
                "size": size if size is not None else base.get("size"),
                "qty": qty,
                # Preserve recorded consent; explicit consent overrides.
                "consent_size": consent_size if consent_size is not None
                else base.get("consent_size"),
            }
            if not effective["message"]:
                raise ValueError("message must not be blank")
            run_id = _next_run_id([r["run_id"] for r in runs])
            now = _db.utcnow()
            conn.execute(
                "INSERT INTO runs (case_id, run_id, thread_id, state, "
                "request_json, created_at, updated_at) "
                "VALUES (?, ?, ?, 'queued', ?, ?, ?)",
                (case_id, run_id, _new_thread_id(case_id, run_id),
                 json.dumps(effective, sort_keys=True), now, now))
            return {"case_id": case_id, "run_id": run_id,
                    "execution_status": "queued", "continued": True,
                    "outcome": None, "reply": None, "exchange_id": None}
    finally:
        conn.close()


def claim_next_run(db_path, worker_id: str = "worker-1") -> dict | None:
    """Atomically claim the oldest queued run whose case is idle."""
    ensure_queue_schema(db_path)
    conn = connect(db_path)
    try:
        with _db.immediate(conn):
            row = conn.execute(
                "SELECT case_id, run_id, thread_id, request_json FROM runs "
                "WHERE state = 'queued' "
                "AND NOT EXISTS (SELECT 1 FROM runs r2 "
                "WHERE r2.case_id = runs.case_id AND r2.state = 'running') "
                "ORDER BY created_at LIMIT 1").fetchone()
            if row is None:
                return None
            updated = conn.execute(
                "UPDATE runs SET state = 'running', updated_at = ? "
                "WHERE case_id = ? AND run_id = ? AND state = 'queued'",
                (_db.utcnow(), row["case_id"], row["run_id"]))
            assert updated.rowcount == 1
            _ = worker_id
            return {"case_id": row["case_id"], "run_id": row["run_id"],
                    "thread_id": row["thread_id"],
                    "request": json.loads(row["request_json"])}
    finally:
        conn.close()


def finish_run(db_path, *, case_id: str, run_id: str, outcome: str | None,
               reply: str | None, exchange_id: str | None,
               error: str | None, trace_id: str | None,
               requests_spent: int | None = None) -> None:
    """Record a run's terminal state. requests_spent is the client-side
    count of model generations consumed (ground truth independent of
    telemetry capture)."""
    state = "completed" if error is None else "failed"
    conn = connect(db_path)
    try:
        with _db.immediate(conn):
            conn.execute(
                "UPDATE runs SET state = ?, outcome = ?, reply = ?, "
                "exchange_id = ?, error = ?, trace_id = ?, "
                "requests_spent = ?, updated_at = ? "
                "WHERE case_id = ? AND run_id = ?",
                (state, outcome, reply, exchange_id, error, trace_id,
                 requests_spent, _db.utcnow(), case_id, run_id))
    finally:
        conn.close()


def mark_interrupted_failed(db_path, reason: str) -> int:
    """Mark leftover running rows failed. Never requeues. Returns count."""
    ensure_queue_schema(db_path)
    conn = connect(db_path)
    try:
        with _db.immediate(conn):
            cur = conn.execute(
                "UPDATE runs SET state = 'failed', error = ?, "
                "updated_at = ? WHERE state = 'running'",
                (reason, _db.utcnow()))
            return cur.rowcount
    finally:
        conn.close()


def _cleanup_state(db_path, exchange_id: str | None) -> str | None:
    if not exchange_id:
        return None
    from .operations import verify_exchange

    try:
        hand = verify_exchange(db_path, exchange_id)
    except Exception:
        return None
    if hand.pending_cleanup:
        return "pending"
    if hand.hold_active:
        return "held"
    return "none"


def _public_status(db_path, conn, case_id: str) -> dict:
    from . import service as _service

    run_rows = conn.execute(
        "SELECT run_id, state, outcome, reply, exchange_id, error, trace_id, "
        "requests_spent FROM runs WHERE case_id = ? ORDER BY rowid",
        (case_id,)).fetchall()
    execution = _case_execution(conn, case_id)
    last = run_rows[-1]
    business = _service.case_status(db_path, case_id)
    if business is not None:
        outcome: str | None = business["outcome"]
        reply: str | None = business["reply"]
        exchange_id: str | None = business["exchange_id"]
        runs = business["runs"]
    else:
        # The agent finished without writing business state (e.g. it
        # stalled with no progress). Report the run's own stored result
        # instead of nulls so status never contradicts the run record.
        outcome = last["outcome"]
        reply = last["reply"]
        exchange_id = last["exchange_id"]
        runs = [r["run_id"] for r in run_rows]
    clarification = reply if outcome == "clarification" else None
    first_request = _case_first_request(conn, case_id)
    return {
        "case_id": case_id,
        "message": _sanitize(first_request.get("message", "")),
        "execution_status": execution,
        "outcome": outcome,
        "reply": reply,
        "exchange_id": exchange_id,
        "runs": sorted(set(runs) | {r["run_id"] for r in run_rows}),
        "current_run_id": last["run_id"],
        "clarification": clarification,
        "cleanup": _cleanup_state(db_path, exchange_id),
        "trace_id": last["trace_id"] if last["trace_id"] else None,
        "error": last["error"] if last["state"] == "failed" else None,
        "requests_spent": last["requests_spent"],
    }


def get_agent_status(db_path, case_id: str) -> dict | None:
    """Responsive read-only agent status. None when unknown to the queue."""
    ensure_queue_schema(db_path)
    conn = connect(db_path)
    try:
        known = conn.execute(
            "SELECT 1 FROM runs WHERE case_id = ? LIMIT 1",
            (case_id,)).fetchone()
        if known is None:
            return None
        return _public_status(db_path, conn, case_id)
    finally:
        conn.close()


def get_agent_timeline(db_path, case_id: str) -> list[dict] | None:
    """Sanitized journal/operations timeline with run ids. None if unknown."""
    from . import service as _service

    ensure_queue_schema(db_path)
    conn = connect(db_path)
    try:
        known = conn.execute(
            "SELECT 1 FROM runs WHERE case_id = ? LIMIT 1",
            (case_id,)).fetchone()
    finally:
        conn.close()
    if known is None:
        return None
    events = _service.case_timeline(db_path, case_id)
    if events is None:
        return []
    conn = connect(db_path)
    try:
        run_of = {r["idempotency_key"]: r["run_id"] for r in conn.execute(
            "SELECT idempotency_key, run_id FROM operations "
            "WHERE case_id = ?", (case_id,))}
    finally:
        conn.close()
    return [{**event, "run_id": run_of.get(event["op_key"])}
            for event in events]


EXECUTION_VALUES = ("queued", "running", "waiting_input", "completed",
                    "failed")
OUTCOME_VALUES = ("arranged", "clarification", "denial", "escalation")

DEFAULT_LIST_LIMIT = 25
MAX_LIST_LIMIT = 100


def _decode_cursor(cursor: str | None) -> tuple[str, str] | None:
    """Decode an opaque page cursor into (created_at, case_id)."""
    if cursor is None:
        return None
    import base64

    try:
        created_at, case_id = base64.urlsafe_b64decode(
            cursor.encode()).decode().split("\n", 1)
        if not created_at or not case_id:
            raise ValueError("empty cursor fields")
        return created_at, case_id
    except Exception:
        raise ValueError("malformed cursor")


def _encode_cursor(created_at: str, case_id: str) -> str:
    import base64

    return base64.urlsafe_b64encode(
        f"{created_at}\n{case_id}".encode()).decode()


def _case_first_request(conn, case_id: str) -> dict:
    row = conn.execute(
        "SELECT request_json FROM runs WHERE case_id = ? ORDER BY rowid "
        "LIMIT 1", (case_id,)).fetchone()
    return json.loads(row["request_json"]) if row else {}


def list_agent_cases(db_path, *, execution: str | None = None,
                     outcome: str | None = None,
                     limit: int = DEFAULT_LIST_LIMIT,
                     cursor: str | None = None) -> dict:
    """List durable agent-path cases, newest first. Read-only: SELECTs only,
    no model calls, no business writes.

    Each item reuses `_public_status` (the same authoritative resolver as
    the detail endpoint), so list and detail always agree — including
    runs without business state (0d8c55a run-outcome fallback).
    `total` and `summary` cover the full filtered population, not the
    page. Suitable for single-store scale (hundreds of cases).
    """
    if execution is not None and execution not in EXECUTION_VALUES:
        raise ValueError(
            f"unknown execution filter; choose one of {EXECUTION_VALUES}")
    if outcome is not None and outcome not in OUTCOME_VALUES:
        raise ValueError(
            f"unknown outcome filter; choose one of {OUTCOME_VALUES}")
    if not isinstance(limit, int) or not 1 <= limit <= MAX_LIST_LIMIT:
        raise ValueError(
            f"limit must be 1-{MAX_LIST_LIMIT}")
    after = _decode_cursor(cursor)
    ensure_queue_schema(db_path)
    conn = connect(db_path)
    try:
        ids = [r["case_id"] for r in conn.execute(
            "SELECT DISTINCT case_id FROM runs")]
        resolved = []
        for case_id in ids:
            try:
                status = _public_status(db_path, conn, case_id)
            except Exception:
                continue
            first = conn.execute(
                "SELECT created_at FROM runs WHERE case_id = ? "
                "ORDER BY rowid LIMIT 1", (case_id,)).fetchone()
            request = _case_first_request(conn, case_id)
            resolved.append((first["created_at"] if first else "", case_id,
                             status, request))
        # Newest first; case_id breaks created_at ties uniquely.
        resolved.sort(key=lambda row: (row[0], row[1]), reverse=True)
        if execution is not None:
            resolved = [r for r in resolved
                        if r[2]["execution_status"] == execution]
        if outcome is not None:
            resolved = [r for r in resolved if r[2]["outcome"] == outcome]
        total = len(resolved)
        summary: dict = {"execution_status": {}, "outcome": {}}
        for _, _, status, _ in resolved:
            bucket = summary["execution_status"]
            bucket[status["execution_status"]] = bucket.get(
                status["execution_status"], 0) + 1
            obucket = summary["outcome"]
            key = status["outcome"] if status["outcome"] is not None \
                else "pending"
            obucket[key] = obucket.get(key, 0) + 1
        arranged = summary["outcome"].get("arranged", 0)
        summary["completion"] = {
            "arranged": arranged,
            "total": total,
            "rate": f"{round(arranged / total * 100)}%"
            if total > 0 else None,
        }
        if after is not None:
            resolved = [r for r in resolved
                        if (r[0], r[1]) < (after[0], after[1])]
        page = resolved[:limit]
        items = []
        for created_at, case_id, status, request in page:
            last_updated = conn.execute(
                "SELECT updated_at FROM runs WHERE case_id = ? "
                "ORDER BY rowid DESC LIMIT 1", (case_id,)).fetchone()
            items.append({
                "case_id": case_id,
                "message": _sanitize(request.get("message", "")),
                "order_id": request.get("order_id"),
                "order_item_id": request.get("order_item_id"),
                "size": request.get("size"),
                "qty": request.get("qty", 1),
                "execution_status": status["execution_status"],
                "outcome": status["outcome"],
                "current_run_id": status["current_run_id"],
                "runs": status["runs"],
                "created_at": created_at,
                "updated_at": last_updated["updated_at"]
                if last_updated else created_at,
                "reply": status["reply"],
            })
        next_cursor = _encode_cursor(page[-1][0], page[-1][1]) \
            if len(resolved) > limit else None
        return {"items": items, "next_cursor": next_cursor, "total": total,
                "summary": summary}
    finally:
        conn.close()


DEFAULT_INVENTORY_LIMIT = 100
MAX_INVENTORY_LIMIT = 500


def read_inventory(db_path, *, sku: str | None = None,
                   size: str | None = None, limit: int = 100,
                   offset: int = 0) -> dict:
    """Read actual stock keyed by SKU and size. Pure read: one SELECT, no
    schema creation, no seeding, no reserve/release/cleanup. Unknown
    database or missing tables read as empty, never an error.

    Ordering is (sku, size); `available = on_hand - held`.
    """
    if not isinstance(limit, int) or not 1 <= limit <= MAX_INVENTORY_LIMIT:
        raise ValueError(f"limit must be 1-{MAX_INVENTORY_LIMIT}")
    if not isinstance(offset, int) or offset < 0:
        raise ValueError("offset must be >= 0")
    read_at = _db.utcnow()
    try:
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
    except Exception:
        return {"items": [], "limit": limit, "offset": offset, "total": 0,
                "read_at": read_at}
    try:
        try:
            clauses, args = [], []
            if sku is not None:
                clauses.append("sku = ?")
                args.append(sku)
            if size is not None:
                clauses.append("size = ?")
                args.append(size)
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            total = conn.execute(
                f"SELECT COUNT(*) AS n FROM stock {where}", args).fetchone()
            rows = conn.execute(
                f"SELECT sku, size, on_hand, held FROM stock {where} "
                "ORDER BY sku, size LIMIT ? OFFSET ?",
                (*args, limit, offset)).fetchall()
        except sqlite3.OperationalError:
            return {"items": [], "limit": limit, "offset": offset,
                    "total": 0, "read_at": read_at}
        return {
            "items": [{"sku": r["sku"], "size": r["size"],
                       "on_hand": r["on_hand"], "held": r["held"],
                       "available": r["on_hand"] - r["held"]}
                      for r in rows],
            "limit": limit, "offset": offset, "total": total["n"],
            "read_at": read_at,
        }
    finally:
        conn.close()
