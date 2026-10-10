"""Slice 6 baseline runner: the AGENT (never the driver) over frozen cases.

- Fresh database per case; multi-part scripts share one database.
- Real model via build_model; bounded by run_agent's recursion limit
  (default 12 tool calls). No per-run tuning, no expected answers leak:
  the agent sees only a composed customer message.
- Abandonment has no agent-visible signal in the ops, so seeded
  abandonment is expressed as a supervisor-handoff sentence in the
  message. This is documented input construction, not an answer leak:
  eligibility, stock, faults, and outcomes stay hidden.
- Usage/latency/cost recorded per run; global spend aborts past the cap.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Rates: Anthropic Haiku 4.5 list, the estimate basis. The hackathon
# proxy deducts from its own pool at its own rates.
USD_PER_MIN, USD_PER_MOUT = 1.00, 5.00
MAX_SPEND_USD = 5.00

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.harness import fresh_db, snapshot  # noqa: E402
from swapdesk import faults  # noqa: E402
from swapdesk.agent.graph import AgentContext  # noqa: E402
from swapdesk.checker import check_run  # noqa: E402


def case_message(case: dict) -> str:
    """Deterministic customer text. Facts only; no answers leak."""
    item = case["order_item_id"]
    order = case["order_id"]
    size = (case.get("requested_size") or "").strip()
    qty = case.get("qty", 1)
    if not size:
        text = f"I need to exchange {item} on order {order}."
    else:
        text = f"Exchange {item} on order {order} for size {size}."
        if qty > 1:
            text += f" I need {qty} units."
    if case.get("consent_size"):
        text += (f" The customer accepts size {case['consent_size']} "
                 "as a replacement.")
    if case.get("abandon_after"):
        text += (" Actually, the customer is abandoning this request; "
                 "hand it to a human supervisor.")
    return text


def _usage_of(messages: list) -> dict:
    tokens_in, tokens_out = 0, 0
    for msg in messages:
        usage = getattr(msg, "usage_metadata", None) or {}
        tokens_in += usage.get("input_tokens", 0)
        tokens_out += usage.get("output_tokens", 0)
    return {"tokens_in": tokens_in, "tokens_out": tokens_out,
            "cost_usd": round(tokens_in / 1e6 * USD_PER_MIN
                              + tokens_out / 1e6 * USD_PER_MOUT, 6)}


def _run_log(db_path, case_id: str, outcome: dict) -> dict:
    log = {"outcome": outcome["outcome"],
           "exchange_id": outcome["exchange_id"],
           "status": None, "duplicate": False,
           "reason": "", "question": ""}
    data = outcome.get("data", {}) if isinstance(outcome, dict) else {}
    if outcome["outcome"] in ("denied", "denial"):
        log["reason"] = data.get("reason", "")
    elif outcome["outcome"] == "clarification":
        log["question"] = data.get("question", "")
    elif outcome["outcome"] in ("escalated", "escalation"):
        log["reason"] = data.get("reason", "")
    if outcome["exchange_id"]:
        from swapdesk.operations import verify_exchange

        try:
            log["status"] = verify_exchange(
                db_path, outcome["exchange_id"]).status
        except Exception:
            log["status"] = "unknown"
    return log


def _arm(case_id: str, run_id: str, fault_specs: list) -> None:
    for spec in fault_specs:
        faults.inject(f"{case_id}:{run_id}:{spec['step']}",
                      spec["point"], spec.get("times", 1))


def run_one_case(db_path, case: dict, run_id: str = "RUN-1") -> dict:
    """Single agent execution. Exceptions become honest crash records."""
    from swapdesk.agent.graph import run_agent

    ctx = AgentContext(db_path=db_path, case_id=case["case_id"],
                       run_id=run_id, message=case_message(case),
                       consent_size=case.get("consent_size"))
    started = time.perf_counter()
    try:
        out = run_agent(ctx)
        crashed = None
    except Exception as exc:  # noqa: BLE001 - recorded, never hidden
        out = {"outcome": "crashed", "exchange_id": None, "reply": "",
               "messages": []}
        crashed = f"{type(exc).__name__}: {exc}"
    latency = round(time.perf_counter() - started, 2)
    usage = _usage_of(out.get("messages", []))
    log = _run_log(db_path, case["case_id"], out) if not crashed else {
        "outcome": "crashed", "exchange_id": None, "status": None,
        "duplicate": False, "reason": crashed, "question": ""}
    return {"log": log, "usage": usage, "latency_s": latency,
            "crashed": crashed}


def run_case_all(db_path, baseline: dict, case: dict, repeat: int) -> dict:
    """Mirror the reference scripts, but every step is the live agent."""
    script = case.get("script", "standard")
    faults.clear()
    if script in ("standard",):
        _arm(case["case_id"], "RUN-1", case.get("faults", []))
        try:
            result = run_one_case(db_path, case, "RUN-1")
        finally:
            faults.clear()
        check = check_run(db_path, case, result["log"], baseline,
                          repeat=repeat)
        return {"result": result, "check": check, "second": None}
    if script == "rerun":
        _arm(case["case_id"], "RUN-1", case.get("faults", []))
        try:
            first = run_one_case(db_path, case, "RUN-1")
        finally:
            faults.clear()
        second = run_one_case(db_path, case, "RUN-2")
        second["log"]["duplicate"] = (
            second["log"]["outcome"] == "arranged")
        check = check_run(db_path, case, second["log"], baseline,
                          repeat=repeat)
        return {"result": second, "check": check,
                "second": {"exchange_id": first["log"]["exchange_id"]}}
    if script == "cross_case":
        second_case = dict(case["second_case"])
        _arm(case["case_id"], "RUN-1", case.get("faults", []))
        try:
            run_one_case(db_path, case, "RUN-1")
        finally:
            faults.clear()
        second = run_one_case(db_path, second_case, "RUN-1")
        second["log"]["duplicate"] = (
            second["log"]["outcome"] == "arranged")
        second["log"]["second"] = {"case_id": second_case["case_id"]}
        check = check_run(db_path, case, second["log"], baseline,
                          repeat=repeat)
        return {"result": second, "check": check, "second": None}
    if script == "cancel_fresh":
        _arm(case["case_id"], "RUN-1", case.get("faults", []))
        try:
            result = run_one_case(db_path, case, "RUN-1")
        finally:
            faults.clear()
        check = check_run(db_path, case, result["log"], baseline,
                          repeat=repeat)
        return {"result": result, "check": check, "second": None}
    raise ValueError(f"unknown script {script!r}")


def run_benchmark(cases: list[dict], only: set | None = None,
                  results_path: Path | None = None,
                  max_spend_usd: float = MAX_SPEND_USD) -> dict:
    """Run selected cases, resuming past (case_id, repeat) pairs on disk."""
    done = {}
    if results_path is not None and results_path.exists():
        prior = json.loads(results_path.read_text())
        for run in prior.get("runs", []):
            done[(run["case_id"], run["repeat"])] = run
    runs = list(done.values())
    spend = sum(r.get("cost_usd", 0.0) for r in runs)
    model = os.environ.get("SWAPDESK_MODEL", "claude-haiku")
    stopped = False
    for case in cases:
        if stopped:
            break
        if only and case["case_id"] not in only:
            continue
        for rep in range(1, case.get("repeats", 1) + 1):
            if (case["case_id"], rep) in done:
                continue
            if spend >= max_spend_usd:
                print(f"spend cap ${max_spend_usd:.2f} reached; stopping "
                      f"before {case['case_id']}#{rep}, rest unrun",
                      flush=True)
                stopped = True
                break
            db_path = fresh_db()
            baseline = snapshot(db_path)
            executed = None
            infra_retries = 0
            for _ in range(3):
                executed = run_case_all(db_path, baseline, case, rep)
                if executed["result"]["crashed"] is None:
                    break
                infra_retries += 1
                print(f"  infra crash, retry {infra_retries}/2: "
                      f"{executed['result']['crashed']}", flush=True)
                db_path = fresh_db()
                baseline = snapshot(db_path)
            result, check = executed["result"], executed["check"]
            cost = result["usage"]["cost_usd"]
            spend = round(spend + cost, 6)
            entry = {
                "benchmark_version": "benchmark-v1",
                "agent": "v1", "model": model,
                "case_id": case["case_id"], "repeat": rep,
                "script": case.get("script", "standard"),
                "infra_retries": infra_retries,
                "passed": check.passed and result["crashed"] is None,
                "failures": ([f"crashed: {result['crashed']}"]
                             if result["crashed"] else []) + check.failures,
                "observed": {
                    "outcome": result["log"].get("outcome"),
                    "exchange_id": result["log"].get("exchange_id"),
                    "status": result["log"].get("status"),
                    "duplicate": result["log"].get("duplicate", False),
                },
                "usage": result["usage"], "latency_s": result["latency_s"],
                "cost_usd": cost,
            }
            runs.append(entry)
            done[(case["case_id"], rep)] = entry
            if results_path is not None:
                # Atomic write: a full disk or crash can never leave a
                # truncated results file behind.
                tmp_path = results_path.with_suffix(".tmp")
                tmp_path.write_text(json.dumps(
                    {"generated_at": datetime.now(timezone.utc).isoformat(
                        timespec="seconds"),
                     "total": len(runs),
                     "passed": sum(1 for r in runs if r.get("passed")),
                     "failed": sum(1 for r in runs if not r.get("passed")),
                     "spend_usd": spend,
                     "runs": runs}, indent=2, sort_keys=True) + "\n")
                os.replace(tmp_path, results_path)
            print(f"[{len(runs)}] {case['case_id']}#{rep} "
                  f"{'PASS' if entry['passed'] else 'FAIL'} "
                  f"{entry['observed'].get('outcome')} "
                  f"${cost:.4f} (spend ${spend:.4f})", flush=True)
    passed = sum(1 for r in runs if r.get("passed"))
    return {"total": len(runs), "passed": passed,
            "failed": len(runs) - passed, "spend_usd": spend, "runs": runs}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="eval/results/baseline_v1.json")
    parser.add_argument("--only", default="",
                        help="comma-separated case ids to run")
    parser.add_argument("--max-spend", type=float, default=MAX_SPEND_USD)
    args = parser.parse_args()
    doc = json.loads(Path("eval/cases_v1.json").read_text())
    only = set(args.only.split(",")) if args.only else None
    summary = run_benchmark(doc["cases"], only=only,
                            results_path=Path(args.out),
                            max_spend_usd=args.max_spend)
    print(f"total={summary['total']} passed={summary['passed']} "
          f"failed={summary['failed']} spend=${summary['spend_usd']:.4f}")
