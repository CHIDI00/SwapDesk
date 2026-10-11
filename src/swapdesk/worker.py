"""Single worker for the customer agent path. One concern only: plumbing.

Claims queued runs atomically and executes each exactly once through
service.submit_agent_ticket — the one agent execution implementation —
with the run's saved request. Results (or sanitized failures) land in
the runs record; status reads derive from saved state.

Reliability rules:
- Paid executions are never retried automatically. A failed run stays
  failed until an explicit continue queues a fresh RUN-n.
- An explicit wall-clock timeout bounds each execution
  (SWAPDESK_RUN_TIMEOUT_S, default 300). Cancellation limits: an
  in-flight model call cannot be cancelled, so on timeout the worker
  records failure and moves on while the orphaned attempt may still
  commit. That is safe but not free: operation keys are idempotent, so
  a late commit cannot double-apply, and no retry is queued for it.
- Startup marks leftover `running` rows failed without replaying them.

Startup: `uv run python -m swapdesk.worker`
"""

from __future__ import annotations

import contextlib
import os
import threading
import time
from pathlib import Path

from . import queue as _queue
from . import service as _service
from . import telemetry as _telemetry
from .agent.capped import BudgetExceeded
from .agent.graph import ConfigurationError
from .agent.request_budget import RequestBudget


def default_budget() -> int:
    try:
        return int(os.environ.get("SWAPDESK_AGENT_BUDGET", "12"))
    except ValueError:
        return 12


def default_timeout_s() -> float:
    try:
        return float(os.environ.get("SWAPDESK_RUN_TIMEOUT_S", "300"))
    except ValueError:
        return 300.0


def _sanitized_agent_error(exc: BaseException) -> str:
    if isinstance(exc, (ConfigurationError, BudgetExceeded)):
        return str(exc)
    return (f"agent execution failed ({type(exc).__name__}); explicit "
            "continue required, no automatic retry")


def execute_run(db_path, *, case_id: str, run_id: str,
                model_factory=None,
                max_requests: int | None = None,
                timeout_s: float | None = None) -> dict:
    """Execute one claimed run exactly once. Returns the stored outcome."""
    _queue.ensure_queue_schema(db_path)
    claimed = _load_claimed(db_path, case_id, run_id)
    request = claimed["request"]
    if max_requests is None:
        max_requests = default_budget()
    if timeout_s is None:
        timeout_s = default_timeout_s()

    model = model_factory() if model_factory is not None else None
    budget = RequestBudget(max_requests)
    outcome: dict | None = None
    error: BaseException | None = None

    def _target():
        nonlocal outcome, error
        try:
            outcome = _service.submit_agent_ticket(
                db_path,
                message=request["message"],
                order_id=request.get("order_id"),
                order_item_id=request.get("order_item_id"),
                size=request.get("size"),
                qty=request.get("qty", 1),
                consent_size=request.get("consent_size"),
                case_id=case_id,
                resume=(run_id != "RUN-1"),
                run_id=run_id,
                model=model,
                middleware=[budget])
        except BaseException as exc:  # noqa: BLE001 - recorded below
            error = exc

    thread = threading.Thread(target=_target, daemon=True,
                              name=f"swapdesk-{case_id}-{run_id}")
    _telemetry.init_telemetry()
    try:
        thread.start()
        thread.join(timeout_s)
        if thread.is_alive():
            _queue.finish_run(
                db_path, case_id=case_id, run_id=run_id, outcome=None,
                reply=None, exchange_id=None, trace_id=None,
                requests_spent=budget.spent,
                error=f"execution timed out after {timeout_s:g}s; the "
                      "in-flight attempt cannot be cancelled and no retry "
                      "was queued; explicit continue required")
            return {"case_id": case_id, "run_id": run_id, "outcome": None,
                    "error": "timed out", "trace_id": None}
        if error is not None:
            cause = getattr(error, "__cause__", None)
            signal = cause if isinstance(
                cause, (ConfigurationError, BudgetExceeded)) else None
            if isinstance(error, _service.AgentExecutionError) \
                    and signal is None:
                message = _sanitized_agent_error(error)
            else:
                message = _sanitized_agent_error(
                    signal if signal is not None else error)
            _queue.finish_run(
                db_path, case_id=case_id, run_id=run_id, outcome=None,
                reply=None, exchange_id=None, trace_id=None,
                requests_spent=budget.spent, error=message)
            return {"case_id": case_id, "run_id": run_id, "outcome": None,
                    "error": message, "trace_id": None}
        assert outcome is not None
        thread_id = f"{case_id}:{run_id}"
        _queue.finish_run(
            db_path, case_id=case_id, run_id=run_id,
            outcome=outcome["outcome"], reply=outcome["reply"],
            exchange_id=outcome["exchange_id"], error=None,
            trace_id=thread_id, requests_spent=budget.spent)
        return {"case_id": case_id, "run_id": run_id,
                "outcome": outcome["outcome"], "reply": outcome["reply"],
                "exchange_id": outcome["exchange_id"], "trace_id": thread_id}
    finally:
        # Every path flushes before returning: success, recorded
        # failure, and timeout. --once therefore never exits with
        # unflushed spans; the polling loop relies on the same guarantee.
        _telemetry.flush()


def _load_claimed(db_path, case_id: str, run_id: str) -> dict:
    import json

    from .db import connect

    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT request_json FROM runs WHERE case_id = ? AND run_id = ?",
            (case_id, run_id)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise ValueError(f"unknown run {case_id!r} {run_id!r}")
    return {"request": json.loads(row["request_json"])}


def drain_once(db_path, *, model_factory=None,
               **kwargs) -> bool:
    """Claim and execute a single queued run. False when idle."""
    claimed = _queue.claim_next_run(db_path)
    if claimed is None:
        return False
    execute_run(db_path, case_id=claimed["case_id"], run_id=claimed["run_id"],
                model_factory=model_factory, **kwargs)
    return True


def mark_startup_interrupted(db_path) -> int:
    return _queue.mark_interrupted_failed(
        db_path, "interrupted: worker stopped before completion; "
        "explicit continue required, no automatic replay")


def main(argv: list[str] | None = None) -> int:
    """Run the worker. `--once` drains the queue and exits (rehearsals,
    controlled runs); default polls forever. Returns process exit code."""
    import argparse

    parser = argparse.ArgumentParser(prog="swapdesk.worker")
    parser.add_argument("--once", action="store_true",
                        help="claim and execute queued runs until idle, "
                             "then exit instead of polling forever")
    args = parser.parse_args(argv)
    db_path = _queue.default_db_path()
    poll_ms = int(os.environ.get("SWAPDESK_WORKER_POLL_MS", "200"))
    worker_id = os.environ.get("SWAPDESK_WORKER_ID", "worker-1")
    recovered = mark_startup_interrupted(db_path)
    print(f"swapdesk worker {worker_id} on {db_path} "
          f"(recovered {recovered} interrupted runs, no replay)",
          flush=True)
    if args.once:
        while drain_once(db_path):
            pass
        return 0
    with contextlib.suppress(KeyboardInterrupt):
        while True:
            claimed = _queue.claim_next_run(db_path, worker_id)
            if claimed is None:
                time.sleep(max(poll_ms, 50) / 1000)
                continue
            print(f"executing {claimed['case_id']} {claimed['run_id']} "
                  f"via agent service path", flush=True)
            execute_run(db_path, case_id=claimed["case_id"],
                        run_id=claimed["run_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
