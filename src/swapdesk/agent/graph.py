"""Agent orchestration: one tool-using loop, bounded and resumable.

One concern only: running a case. The model chooses tools from observed
results; the outcome and the customer reply are derived from database
state afterwards, never from model prose. Orchestration checkpoints
(LangGraph threads) are separate from business-action records: resuming
reuses the same tool keys, so backend idempotency still governs effects.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import neatlogs

from .. import telemetry
from ..operations import get_case, verify_exchange
from .prompts import (
    OUTCOME_ARRANGED,
    OUTCOME_CLARIFICATION,
    OUTCOME_DENIAL,
    OUTCOME_ESCALATION,
    SYSTEM_PROMPT,
    render_reply,
)
from .tools import ToolContext, build_tools

DEFAULT_MAX_TOOL_CALLS = 12


class ConfigurationError(Exception):
    """Agent misconfiguration (e.g. no model selected)."""


@dataclass(frozen=True)
class AgentContext:
    db_path: str | Path
    case_id: str
    run_id: str
    message: str
    consent_size: str | None = None
    order_id: str | None = None
    order_item_id: str | None = None
    requested_size: str | None = None
    qty: int = 1


# User-specified direct-Gemini model. Override with SWAPDESK_MODEL.
DEFAULT_MODEL_ID = "gemini-3.8-flash"

# Hackathon LiteLLM proxy (OpenAI-compatible). Override with LITELLM_BASE_URL.
LITELLM_DEFAULT_BASE_URL = "https://litellm.vision.aivar.app/v1"
LITELLM_DEFAULT_MODEL_ID = "claude-haiku"


def resolve_model_id(explicit: str | None = None) -> str:
    """Model id: explicit arg, else SWAPDESK_MODEL, else the default."""
    return explicit or os.environ.get("SWAPDESK_MODEL") or DEFAULT_MODEL_ID


def build_model(model_id: str | None = None):
    """Provider chat model from environment, never hardcoded to one.

    LITELLM_API_KEY present → OpenAI-compatible client at the LiteLLM
    proxy (hackathon key). Else GEMINI_API_KEY → direct Gemini. Else a
    clear ConfigurationError. SDK retries are disabled on both paths:
    every request is exactly one attempt, so a middleware request cap
    means what it says.
    """
    telemetry.load_dotenv()
    if "LITELLM_API_KEY" in os.environ:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_id or os.environ.get("SWAPDESK_MODEL")
            or LITELLM_DEFAULT_MODEL_ID,
            base_url=os.environ.get("LITELLM_BASE_URL",
                                    LITELLM_DEFAULT_BASE_URL),
            api_key=os.environ["LITELLM_API_KEY"],
            max_retries=0)
    if "GEMINI_API_KEY" in os.environ:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=resolve_model_id(model_id),
                                      max_retries=0)
    raise ConfigurationError(
        "no model provider configured: set LITELLM_API_KEY (plus "
        "SWAPDESK_MODEL) or GEMINI_API_KEY; nothing was called")


def build_agent(ctx: AgentContext, model=None, checkpointer=None, *,
                middleware=(), state_schema=None, interrupt_after=None,
                telemetry_enabled=True):
    """Compile one agent for one case run. Checkpointer may be shared."""
    from langchain.agents import create_agent

    if telemetry_enabled:
        telemetry.init_telemetry()
    model = model or build_model()
    if telemetry_enabled:
        model = telemetry.maybe_wrap_gemini(model)
    tools = build_tools(ToolContext(
        db_path=ctx.db_path, case_id=ctx.case_id, run_id=ctx.run_id,
        order_id=ctx.order_id, order_item_id=ctx.order_item_id,
        requested_size=ctx.requested_size, qty=ctx.qty))
    return create_agent(model, tools, system_prompt=SYSTEM_PROMPT,
                        checkpointer=checkpointer, middleware=list(middleware),
                        state_schema=state_schema, interrupt_after=interrupt_after)


def compose_input(message: str, case_id: str, run_id: str,
                  consent_size: str | None = None) -> str:
    """Production input composition, shared by direct and Studio runs."""
    lines = [f"case_id: {case_id}", f"run_id: {run_id}"]
    if consent_size:
        lines.append(f"recorded customer consent: accepts size "
                     f"{consent_size} as a replacement")
    lines.append(f"customer message: {message}")
    return "\n".join(lines)


def _latest_note(case: dict | None, state: str) -> str:
    if not case:
        return ""
    notes = case.get("progress", {}).get("notes", [])
    for note in reversed(notes):
        if note.get("state") == state:
            return note.get("detail", "")
    return ""


def _case_exchange(db_path, case_id: str):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT * FROM exchanges WHERE case_id = ?"
            " ORDER BY rowid DESC LIMIT 1",
            (case_id,)).fetchone()
    finally:
        conn.close()


def _case_exchange_or_reused(db_path, case_id: str):
    """This case's latest exchange, else the duplicate-reused one named
    by its operation records."""
    row = _case_exchange(db_path, case_id)
    if row is not None:
        return row
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        op = conn.execute(
            "SELECT result_json FROM operations WHERE case_id = ? "
            "ORDER BY rowid DESC LIMIT 1", (case_id,)).fetchone()
        if op is None:
            return None
        try:
            exchange_id = json.loads(op["result_json"]).get("exchange_id")
        except ValueError:
            return None
        if not exchange_id:
            return None
        return conn.execute("SELECT * FROM exchanges WHERE id = ?",
                            (exchange_id,)).fetchone()
    finally:
        conn.close()


def _escalation_reason(db_path, exchange_id: str) -> str:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT details_json FROM journal WHERE event = 'released'"
            " ORDER BY rowid DESC LIMIT 25").fetchall()
    finally:
        conn.close()
    for row in rows:
        try:
            details = json.loads(row["details_json"])
        except ValueError:
            continue
        if details.get("exchange_id") == exchange_id:
            return details.get("reason", "")
    return ""


def derive_outcome(ctx: AgentContext) -> dict:
    """Decide the outcome from persisted state. The model is not asked."""
    case = get_case(ctx.db_path, ctx.case_id)
    state = case["state"] if case else None
    if state == "arranged":
        row = _case_exchange_or_reused(ctx.db_path, ctx.case_id)
        if row is None:
            return {"outcome": OUTCOME_ESCALATION, "exchange_id": None,
                    "data": {"reason": "arranged case has no exchange row",
                             "partial": "data inconsistent"}}
        hand = verify_exchange(ctx.db_path, row["id"])
        return {"outcome": OUTCOME_ARRANGED, "exchange_id": row["id"],
                "data": {"exchange_id": row["id"],
                         "return_id": hand.return_id,
                         "label_id": hand.label_id,
                         "tracking_ref": hand.tracking_ref}}
    if state == "denied":
        return {"outcome": OUTCOME_DENIAL, "exchange_id": None,
                "data": {"reason": _latest_note(case, "denied")}}
    if state == "needs_information":
        return {"outcome": OUTCOME_CLARIFICATION, "exchange_id": None,
                "data": {"question": _latest_note(case, "needs_information")}}
    if state in ("escalated", "cleanup_pending"):
        row = _case_exchange(ctx.db_path, ctx.case_id)
        if row is None:
            return {"outcome": OUTCOME_ESCALATION, "exchange_id": None,
                    "data": {"reason": _latest_note(case, "escalated"),
                             "partial": "no exchange started"}}
        hand = verify_exchange(ctx.db_path, row["id"])
        partial = (f"{hand.status}, hold "
                   f"{'active' if hand.hold_active else 'released'}, "
                   f"return {hand.return_id or 'none'}, "
                   f"label {hand.label_id or 'none'}")
        return {"outcome": OUTCOME_ESCALATION, "exchange_id": row["id"],
                "data": {"reason": _escalation_reason(ctx.db_path, row["id"]),
                         "partial": partial}}
    return {"outcome": OUTCOME_ESCALATION, "exchange_id": None,
            "data": {"reason": "agent made no progress",
                     "partial": f"case state {state!r}"}}


def run_agent(ctx: AgentContext, model=None, checkpointer=None,
              max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS) -> dict:
    """Run one case to a verified outcome. Bounded; flushes telemetry."""
    agent = build_agent(ctx, model=model, checkpointer=checkpointer)
    config = {"configurable": {
                  "thread_id": f"{ctx.case_id}:{ctx.run_id}"},
              "recursion_limit": 2 * max_tool_calls + 5}
    try:
        with neatlogs.trace(f"swapdesk:{ctx.case_id}",
                             kind="WORKFLOW") as span:
            span.set_attribute("swapdesk.case_id", ctx.case_id)
            span.set_attribute("swapdesk.run_id", ctx.run_id)
            span.set_attribute("swapdesk.benchmark",
                               telemetry.BENCHMARK_VERSION)
            if ctx.consent_size:
                span.set_attribute("swapdesk.consent_size", ctx.consent_size)
            result = agent.invoke(
                {"messages": [{"role": "user",
                               "content": compose_input(
                                   ctx.message, ctx.case_id, ctx.run_id,
                                   ctx.consent_size)}]},
                config)
            decided = derive_outcome(ctx)
            reply = render_reply(decided["outcome"], decided["data"])
            neatlogs.log("case {case_id} -> {outcome}",
                         case_id=ctx.case_id, outcome=decided["outcome"])
            return {"outcome": decided["outcome"],
                    "exchange_id": decided["exchange_id"],
                    "reply": reply,
                    "messages": result["messages"],
                    "data": decided["data"],
                    "exporting": telemetry.is_exporting()}
    finally:
        telemetry.flush()


@contextmanager
def sqlite_checkpointer(path: str | Path):
    """File-backed LangGraph checkpointer, separate from business data."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    from langgraph.checkpoint.sqlite import SqliteSaver

    # Same-thread check off: the graph may execute nodes on worker threads.
    # Still one local file, never shared between processes.
    conn = sqlite3.connect(str(path), check_same_thread=False)
    try:
        yield SqliteSaver(conn)
    finally:
        conn.close()
