"""Studio verification flows over the real backend. One concern only.

Two compiled graphs share one architecture (prepare -> agent -> verify):

- offline (default): a scripted model replays tool calls against the real
  backend. Zero model requests. This is wiring verification, never proof
  of Gemini's decisions.
- live (opt-in): a budget-capped Gemini model. Requires an explicit
  request budget plus SWAPDESK_MODEL and GEMINI_API_KEY; anything missing
  fails loudly before any model call. Never a silent fake success.

The agent itself is always the nested production graph from build_agent()
(same tools, same prompts, same bounded loop), compiled here WITHOUT its
own checkpointer so the parent thread owns persistence. Studio renders it
as a subgraph: expand it to inspect every model turn, tool call, and
tool result. Individual tools share one ToolNode because that is how the
prebuilt agent compiles a tool list; the shared node does not hide
anything, each call still lands as its own ToolMessage in the trace.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TypedDict

import neatlogs
from langgraph.graph import END, StateGraph

from .. import faults as _faults
from .. import telemetry
from ..db import connect, init_db
from ..fixtures import load_fixtures
from ..operations import get_case
from .capped import BudgetExceeded, BudgetedChatModel
from .graph import (
    AgentContext,
    ConfigurationError,
    build_agent,
    derive_outcome,
)
from .prompts import render_reply
from .scripted import SCENARIOS, WIRING_LABEL, script_for

STUDIO_ROOT = Path("studio_data")
THREADS_DB = STUDIO_ROOT / "studio_threads.db"
DEFAULT_RUN_ID = "RUN-1"


def _studio_root() -> Path:
    """Studio data dir; SWAPDESK_STUDIO_ROOT overrides (tests stay out of
    the repo working tree)."""
    override = os.environ.get("SWAPDESK_STUDIO_ROOT")
    return Path(override) if override else STUDIO_ROOT


class StudioState(TypedDict, total=False):
    mode: str
    scenario: str
    message: str
    case_id: str
    run_id: str
    resume: bool
    budget: int | None
    consent_size: str | None
    db_path: str
    outcome: str | None
    reply: str | None
    exchange_id: str | None
    evidence: dict
    agent_trace: list
    error: str | None


def default_case_id(scenario: str) -> str:
    return f"DEMO-{scenario.upper()}"


def _case_db(case_id: str) -> Path:
    return _studio_root() / case_id / "shop.db"


def _scenario_faults(scenario: str, case_id: str, run_id: str) -> list:
    if scenario == "recover":
        return [(f"{case_id}:{run_id}:reserve", "crash", 1)]
    return []


def prepare(state: StudioState) -> dict:
    """Seed (or resume) one isolated synthetic case. Never resets one."""
    mode = state.get("mode", "offline")
    scenario = state.get("scenario", "arrange")
    if scenario not in SCENARIOS:
        return {"error": f"unknown scenario {scenario!r}; "
                         f"choose one of {sorted(SCENARIOS)}"}
    case_id = state.get("case_id") or default_case_id(scenario)
    run_id = state.get("run_id") or DEFAULT_RUN_ID
    resume = bool(state.get("resume", False))
    message = state.get("message") or SCENARIOS[scenario]["message"]

    if mode == "live":
        budget = state.get("budget")
        if not isinstance(budget, int) or budget < 1:
            return {"error": "live mode needs an explicit request budget, "
                             'e.g. {"budget": 5}; no model calls made'}

    db_path = _case_db(case_id)
    if db_path.exists():
        if not resume:
            return {"error": f"case {case_id!r} is already active; pass "
                             '"resume": true to continue it or choose a new '
                             "case_id. Nothing was reset"}
    else:
        if resume:
            return {"error": f"nothing to resume for case {case_id!r}; "
                             "drop \"resume\" to seed a fresh case"}
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = connect(db_path)
        try:
            init_db(conn)
            load_fixtures(conn)
        finally:
            conn.close()
    return {"mode": mode, "scenario": scenario, "case_id": case_id,
            "run_id": run_id, "resume": resume, "message": message,
            "consent_size": state.get("consent_size"),
            "budget": state.get("budget"), "db_path": str(db_path),
            "error": None}


def _trace_messages(result: dict) -> list:
    trace = []
    for msg in result.get("messages", []):
        kind = type(msg).__name__
        if kind == "AIMessage" and getattr(msg, "tool_calls", None):
            trace.append({"role": "model",
                          "calls": [(c["name"], c["args"])
                                    for c in msg.tool_calls]})
        elif kind == "ToolMessage":
            trace.append({"role": "tool", "name": getattr(msg, "name", ""),
                          "content": str(msg.content)[:400]})
        else:
            trace.append({"role": kind,
                          "content": str(getattr(msg, "content", ""))[:200]})
    return trace


def _ctx_from(state: StudioState) -> AgentContext:
    return AgentContext(db_path=state["db_path"], case_id=state["case_id"],
                        run_id=state["run_id"], message=state["message"],
                        consent_size=state.get("consent_size"))


def offline_agent(state: StudioState) -> dict:
    """Run the nested production graph with a scripted model."""
    from .scripted import ScriptedChatModel

    ctx = _ctx_from(state)
    model = ScriptedChatModel(
        script_for(state["scenario"], ctx.case_id, ctx.run_id))
    sub = build_agent(ctx, model=model)
    for key, point, times in _scenario_faults(state["scenario"],
                                              ctx.case_id, ctx.run_id):
        _faults.inject(key, point, times)
    try:
        result = sub.invoke(
            {"messages": [{"role": "user", "content": state["message"]}]},
            {"recursion_limit": 30})
    finally:
        _faults.clear()
    return {"agent_trace": _trace_messages(result)}


def _require_live_config() -> str:
    telemetry.load_dotenv()
    model_id = os.environ.get("SWAPDESK_MODEL")
    if not model_id:
        raise ConfigurationError(
            "live mode needs SWAPDESK_MODEL set to a Gemini model id; "
            "nothing was called")
    if "GEMINI_API_KEY" not in os.environ:
        raise ConfigurationError(
            "live mode needs GEMINI_API_KEY in the environment or .env; "
            "nothing was called")
    return model_id


def live_agent(state: StudioState) -> dict:
    """Run the nested production graph with a budget-capped Gemini model."""
    budget = state.get("budget")
    try:
        model_id = _require_live_config()
    except ConfigurationError as exc:
        return {"error": str(exc)}
    ctx = _ctx_from(state)
    model = telemetry.maybe_wrap_gemini(
        BudgetedChatModel(model=model_id).set_budget(budget))
    sub = build_agent(ctx, model=model)
    try:
        with neatlogs.trace(f"swapdesk-studio:{ctx.case_id}",
                             kind="WORKFLOW") as span:
            span.set_attribute("swapdesk.case_id", ctx.case_id)
            span.set_attribute("swapdesk.run_id", ctx.run_id)
            span.set_attribute("swapdesk.mode", "live")
            span.set_attribute("swapdesk.budget", budget)
            result = sub.invoke(
                {"messages": [{"role": "user", "content": state["message"]}]},
                {"recursion_limit": 2 * 12 + 5})
    except BudgetExceeded as exc:
        spent = getattr(model, "spent", "?")
        return {"error": f"{exc} (spent {spent}); state kept, no fake reply"}
    finally:
        telemetry.flush()
    return {"agent_trace": _trace_messages(result)}


def verify(state: StudioState) -> dict:
    """Derive the outcome from persisted state; render the reply."""
    ctx = _ctx_from(state)
    decided = derive_outcome(ctx)
    reply = render_reply(decided["outcome"], decided["data"])
    conn = connect(ctx.db_path)
    try:
        case_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM exchanges WHERE case_id = ?", (ctx.case_id,))]
        case_ops = [dict(r) for r in conn.execute(
            "SELECT idempotency_key, op_type, status FROM operations "
            "WHERE case_id = ?", (ctx.case_id,))]
        case = get_case(ctx.db_path, ctx.case_id)
    finally:
        conn.close()
    evidence = {
        "mode": state.get("mode"),
        "label": WIRING_LABEL if state.get("mode") == "offline"
        else "live Gemini run",
        "outcome": decided["outcome"],
        "exchange_id": decided["exchange_id"],
        "reply": reply,
        "exchanges": case_rows,
        "operations": case_ops,
        "case_state": case["state"] if case else None,
    }
    return {"outcome": decided["outcome"], "reply": reply,
            "exchange_id": decided["exchange_id"], "evidence": evidence}


def _after_prepare(state: StudioState) -> str:
    return "error" if state.get("error") else "agent"


def _builder(mode: str):
    def _prepare(state: StudioState) -> dict:
        # The graph defines the mode; input cannot smuggle the other one.
        return prepare({**state, "mode": mode})

    graph = StateGraph(StudioState)
    graph.add_node("prepare", _prepare)
    graph.add_node("agent", offline_agent if mode == "offline"
                   else live_agent)
    graph.add_node("verify", verify)
    graph.add_node("error", lambda state: {})
    graph.set_entry_point("prepare")
    graph.add_conditional_edges("prepare", _after_prepare,
                                {"agent": "agent", "error": "error"})
    graph.add_edge("agent", "verify")
    graph.add_edge("verify", END)
    graph.add_edge("error", END)
    return graph


def build_offline_graph(checkpointer=None):
    """Studio default: scripted model, zero model requests."""
    return _builder("offline").compile(checkpointer=checkpointer)


def build_live_graph(checkpointer=None):
    """Opt-in live Gemini with an explicit per-run request budget."""
    return _builder("live").compile(checkpointer=checkpointer)
