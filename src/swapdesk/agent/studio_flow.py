"""Studio's inspectable agent subgraph, isolated cases, offline-first runs.

The compiled production agent is registered directly as the `agent` node.
Middleware binds its model and tools to the prepared case without recompiling
or hiding the model/tools loop. Shared message state is checkpointed by the
parent/serving platform. No model client is constructed at graph import.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from uuid import uuid4

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ExtendedModelResponse, ModelResponse
from langchain_core.messages import AIMessage, RemoveMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.types import Command

from .. import faults, telemetry
from ..db import connect, init_db
from ..fixtures import load_fixtures
from ..operations import get_case
from .capped import BudgetExceeded, BudgetedChatModel
from .graph import AgentContext, ConfigurationError, build_agent, derive_outcome, compose_input
from .prompts import render_reply
from .scripted import SCENARIOS, WIRING_LABEL, ScriptedChatModel, script_for
from .tools import ToolContext, build_tools

STUDIO_ROOT = Path("studio_data")


class StudioState(AgentState, total=False):
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
    script_cursor: int
    requests_spent: int
    generated_case_id: str | None
    generated_run_id: str | None


def _studio_root() -> Path:
    return Path(os.environ.get("SWAPDESK_STUDIO_ROOT") or STUDIO_ROOT).resolve()


def default_case_id(scenario: str) -> str:
    return f"DEMO-{scenario.upper()}-{uuid4().hex[:12]}"


def _identity(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", value):
        raise ValueError(f"{label} must use 1–96 letters, digits, underscores or hyphens")
    return value


def _case_db(case_id: str) -> Path:
    root = _studio_root()
    candidate = (root / _identity(case_id, "case_id") / "shop.db").resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("case path escapes the Studio data directory")
    return candidate


def _ctx_from(state) -> AgentContext:
    return AgentContext(db_path=state["db_path"], case_id=state["case_id"],
                        run_id=state["run_id"], message=state["message"],
                        consent_size=state.get("consent_size"))


def _require_live_config() -> str:
    telemetry.load_dotenv()
    model_id = os.environ.get("SWAPDESK_MODEL")
    if not model_id:
        raise ConfigurationError("live mode needs SWAPDESK_MODEL; no model calls made")
    if not os.environ.get("GEMINI_API_KEY"):
        raise ConfigurationError("live mode needs GEMINI_API_KEY; no model calls made")
    return model_id


def _cleared():
    return {"outcome": None, "reply": None, "exchange_id": None,
            "evidence": {}, "agent_trace": [], "error": None}


def prepare(state: StudioState) -> dict:
    """Initialize a fresh synthetic case or explicitly continue its identity."""
    cleared = _cleared()
    try:
        mode = state.get("mode") or "offline"
        scenario = state.get("scenario") or "arrange"
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario; choose {sorted(SCENARIOS)}")
        resume = state.get("resume", False)
        if type(resume) is not bool:
            raise ValueError("resume must be true or false")
        if resume and (not state.get("case_id") or not state.get("run_id")):
            raise ValueError("resume requires the original case_id and run_id")
        requested_case = state.get("case_id")
        requested_run = state.get("run_id")
        if not resume and requested_case == state.get("generated_case_id"):
            requested_case = None
        if not resume and requested_run == state.get("generated_run_id"):
            requested_run = None
        case_id = _identity(requested_case or default_case_id(scenario), "case_id")
        run_id = _identity(requested_run or f"RUN-{uuid4().hex[:12]}", "run_id")
        budget = state.get("budget")
        if mode == "live":
            if type(budget) is not int or budget < 1:
                raise ValueError("live mode needs an explicit positive integer budget; no model calls made")
            _require_live_config()  # before touching the demo database
        db_path = _case_db(case_id)
        manifest = db_path.parent / "identity.json"
        exists = db_path.exists()
        if exists and not resume:
            raise ValueError("case is already active; use original case_id/run_id with resume=true or a new case_id; nothing was reset")
        if resume and not exists:
            raise ValueError("nothing to resume for this case")
        saved = {}
        if exists:
            if not manifest.exists():
                raise ValueError("case has no identity manifest; use a fresh case_id")
            saved = json.loads(manifest.read_text())
            if saved.get("run_id") != run_id or saved.get("scenario") != scenario or saved.get("mode") != mode:
                raise ValueError("resume must preserve the original run_id, scenario and mode")
        else:
            db_path.parent.mkdir(parents=True, exist_ok=False)
            conn = connect(db_path)
            try:
                init_db(conn)
                load_fixtures(conn)
            finally:
                conn.close()
            manifest.write_text(json.dumps({"run_id": run_id, "scenario": scenario, "mode": mode}))
            conn = connect(db_path)
            try:
                conn.execute("CREATE TABLE studio_request_budget (id INTEGER PRIMARY KEY, spent INTEGER NOT NULL)")
                conn.execute("INSERT INTO studio_request_budget VALUES (1, 0)")
                conn.commit()
            finally:
                conn.close()
        message = state.get("message") or SCENARIOS[scenario]["message"]
        update = {**cleared, "mode": mode, "scenario": scenario,
                  "case_id": case_id, "run_id": run_id, "resume": resume,
                  "message": message, "budget": budget,
                  "consent_size": state.get("consent_size"), "db_path": str(db_path),
                  "requests_spent": _spent_on_disk({"case_id": case_id}),
                  "generated_case_id": case_id if not requested_case else None,
                  "generated_run_id": run_id if not requested_run else None}
        ctx = _ctx_from(update)
        if resume:
            if not state.get("messages"):
                raise ValueError("conversation resume requires the original Studio thread; use its saved state")
            # Do not add a new user message between pending AI calls and tool results.
            # Interrupted execution is resumed with graph.invoke(None, same config).
            update["messages"] = []
        else:
            update["script_cursor"] = 0
            update["messages"] = [RemoveMessage(id=REMOVE_ALL_MESSAGES),
                                  {"role": "user",
                                   "content": compose_input(
                                       message, case_id, run_id,
                                       state.get("consent_size"))}]
        return update
    except (ValueError, OSError) as exc:
        return {**cleared, "error": str(exc)}
    except ConfigurationError as exc:
        return {**cleared, "error": str(exc)}


def _trace_messages(result: dict) -> list:
    trace = []
    for msg in result.get("messages", []):
        row = {"role": type(msg).__name__, "content": msg.content}
        if isinstance(msg, AIMessage):
            row["calls"] = [(c["name"], c["args"]) for c in msg.tool_calls]
            row["role"] = "model"
        if type(msg).__name__ == "ToolMessage":
            row.update(role="tool", name=msg.name, tool_call_id=msg.tool_call_id)
        trace.append(row)
    return trace


def _tools_for(state):
    ctx = _ctx_from(state)
    return build_tools(ToolContext(ctx.db_path, ctx.case_id, ctx.run_id))


def _spent_on_disk(state, increment=0):
    """Atomically reserve budget before a generation, including failed attempts.

    SQLite serializes reservations for concurrent submissions of the same case.
    A resume's budget is a cumulative ceiling for its original case/run.
    """
    conn = connect(_case_db(state["case_id"]))
    try:
        conn.execute("BEGIN IMMEDIATE")
        spent = conn.execute("SELECT spent FROM studio_request_budget WHERE id = 1").fetchone()[0]
        if increment:
            if spent >= state["budget"]:
                raise BudgetExceeded(f"model budget exhausted ({spent}/{state['budget']} attempts)")
            conn.execute("UPDATE studio_request_budget SET spent = spent + ? WHERE id = 1", (increment,))
        conn.commit()
        return spent + increment
    finally:
        conn.close()


class StudioMiddleware(AgentMiddleware):
    """Runtime binding for the statically registered production agent."""
    state_schema = StudioState

    def wrap_model_call(self, request, handler):
        state = request.state
        updates = {}
        try:
            if state["mode"] == "offline":
                sequence = script_for(state["scenario"], state["case_id"], state["run_id"])
                cursor = state.get("script_cursor", 0)
                # Scripts exercise actual tools but do not interpret user intent.
                model = ScriptedChatModel(sequence[cursor:cursor+1])
                updates["script_cursor"] = cursor + 1
            else:
                model = BudgetedChatModel(model=_require_live_config()).set_budget(1)
                updates["requests_spent"] = _spent_on_disk(state, 1)
            response = handler(request.override(model=model, tools=_tools_for(state)))
            return ExtendedModelResponse(response, Command(update=updates))
        except (BudgetExceeded, ConfigurationError) as exc:
            error = str(exc)
        except Exception as exc:
            # Provider errors can contain credentials or endpoints. Expose only
            # a type, never raw exception text, in user-visible state.
            error = f"agent model failed ({type(exc).__name__}); inspect local diagnostics"
        if state.get("mode") == "live":
            updates["requests_spent"] = _spent_on_disk(state)
        updates.pop("script_cursor", None)
        updates["error"] = error
        return ExtendedModelResponse(ModelResponse([AIMessage(content="Run stopped; see error state.")]),
                                     Command(update=updates))

    async def awrap_model_call(self, request, handler):
        # Studio's live async requests use the SAME budget reservation path.
        # Select through the sync implementation with a captured request, then
        # await the handler without running provider work on the event loop.
        captured = []
        def capture(changed):
            captured.append(changed)
            return ModelResponse([])
        prepared = self.wrap_model_call(request, capture)
        if not captured:
            return prepared
        try:
            response = await handler(captured[0])
            return ExtendedModelResponse(response, prepared.command)
        except Exception as exc:
            update = dict(prepared.command.update)
            update.pop("script_cursor", None)
            update["error"] = f"agent model failed ({type(exc).__name__}); inspect local diagnostics"
            return ExtendedModelResponse(ModelResponse([AIMessage(content="Run stopped; see error state.")]), Command(update=update))

    def wrap_tool_call(self, request, handler):
        tools = {tool.name: tool for tool in _tools_for(request.state)}
        # Arm only this case's fault, once, at the first reservation. No global
        # clear() which would erase another concurrent offline case's fault.
        state = request.state
        if (state["mode"] == "offline" and state["scenario"] == "recover"
                and request.tool_call["name"] == "reserve_replacement"
                and not any(type(m).__name__ == "ToolMessage" and m.name == "reserve_replacement"
                            for m in state.get("messages", []))):
            faults.inject(f"{state['case_id']}:{state['run_id']}:reserve", "crash", 1)
        return handler(request.override(tool=tools[request.tool_call["name"]]))

    async def awrap_tool_call(self, request, handler):
        # The original tools are synchronous SQLite operations. Use exactly
        # the synchronous binding/error semantics on a worker thread.
        import asyncio
        return await asyncio.to_thread(self.wrap_tool_call, request,
                                       lambda changed: changed.tool.invoke(changed.tool_call))


def _evidence(state):
    ctx = _ctx_from(state)
    conn = connect(ctx.db_path)
    try:
        exchanges = [dict(r) for r in conn.execute("SELECT * FROM exchanges WHERE case_id = ?", (ctx.case_id,))]
        ops = [dict(r) for r in conn.execute("SELECT idempotency_key, op_type, status FROM operations WHERE case_id = ?", (ctx.case_id,))]
        case = get_case(ctx.db_path, ctx.case_id)
    finally:
        conn.close()
    return {"mode": state["mode"], "label": WIRING_LABEL if state["mode"] == "offline" else "live Gemini run",
            "exchanges": exchanges, "operations": ops,
            "case_state": case["state"] if case else None,
            "requests_spent": state.get("requests_spent", 0)}


def verify(state):
    case = get_case(state["db_path"], state["case_id"])
    if not case or case["state"] not in {"arranged", "denied", "needs_information", "escalated", "cleanup_pending"}:
        return {**error_terminal(state), "error": "agent stopped without a persisted terminal case; no customer reply generated"}
    decided = derive_outcome(_ctx_from(state))
    reply = render_reply(decided["outcome"], decided["data"])
    evidence = {**_evidence(state), **decided, "reply": reply}
    return {"outcome": decided["outcome"], "reply": reply,
            "exchange_id": decided["exchange_id"], "evidence": evidence,
            "agent_trace": _trace_messages(state)}


def error_terminal(state):
    update = {"outcome": None, "reply": None, "exchange_id": None,
              "evidence": {}, "agent_trace": _trace_messages(state)}
    if state.get("db_path") and state.get("case_id"):
        try:
            update["evidence"] = {**_evidence(state), "diagnostic_only": True}
        except (OSError, ValueError):
            pass
    return update


def _builder(mode, interrupt_after_tools=False):
    # Static tool signatures at compile time; middleware substitutes only
    # bindings at execution time. Placeholder model cannot call a provider.
    ctx = AgentContext("unused-studio-placeholder.db", "PLACEHOLDER", "PLACEHOLDER", "")
    agent = build_agent(ctx, model=ScriptedChatModel([]), middleware=[StudioMiddleware()],
                        state_schema=StudioState, telemetry_enabled=False,
                        interrupt_after=["tools"] if interrupt_after_tools else None)
    def initial(state):
        return prepare({**state, "mode": mode})
    graph = StateGraph(StudioState)
    graph.add_node("prepare", initial)
    graph.add_node("agent", agent)
    graph.add_node("verify", verify)
    graph.add_node("error", error_terminal)
    graph.set_entry_point("prepare")
    graph.add_conditional_edges("prepare", lambda s: "error" if s.get("error") else "agent", {"error": "error", "agent": "agent"})
    graph.add_conditional_edges("agent", lambda s: "error" if s.get("error") else "verify", {"error": "error", "verify": "verify"})
    graph.add_edge("verify", END)
    graph.add_edge("error", END)
    return graph


def build_offline_graph(checkpointer=None, *, interrupt_after_tools=False):
    return _builder("offline", interrupt_after_tools).compile(checkpointer=checkpointer)


def build_live_graph(checkpointer=None):
    return _builder("live").compile(checkpointer=checkpointer)
