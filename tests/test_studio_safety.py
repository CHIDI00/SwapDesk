"""Studio regressions: real tools, discoverable loop, no provider traffic."""
import asyncio
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from google.genai import types

from swapdesk.agent import studio_flow as flow
from swapdesk.agent.capped import BudgetExceeded, BudgetedChatModel
from swapdesk.agent.graph import sqlite_checkpointer
from swapdesk import faults


@pytest.fixture(autouse=True)
def hermetic(monkeypatch, tmp_path):
    monkeypatch.setenv("SWAPDESK_TELEMETRY_ENV", "0")
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("SWAPDESK_MODEL", raising=False)
    monkeypatch.setenv("SWAPDESK_STUDIO_ROOT", str(tmp_path / "studio"))
    faults.clear()
    yield
    faults.clear()


def _symlinks_allowed() -> bool:
    try:
        with tempfile.TemporaryDirectory() as probe:
            Path(probe, "link").symlink_to(probe, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        return False


requires_symlink = pytest.mark.skipif(
    not _symlinks_allowed(),
    reason="this user/machine cannot create symlinks (e.g. Windows "
           "without Developer Mode); path-escape guard still reviewed")


def test_compiled_agent_subgraph_is_discoverable():
    graph = flow.build_offline_graph()
    subgraphs = dict(graph.get_subgraphs(recurse=True))
    assert "agent" in subgraphs
    nodes = subgraphs["agent"].get_graph().nodes
    assert {"model", "tools"} <= set(nodes)
    assert {"agent:model", "agent:tools"} <= set(graph.get_graph(xray=True).nodes)


def test_repeat_default_runs_on_persisted_thread_are_fresh(tmp_path):
    with sqlite_checkpointer(tmp_path / "threads.db") as saver:
        graph = flow.build_offline_graph(saver)
        cfg = {"configurable": {"thread_id": "fresh-runs"}}
        a = graph.invoke({"scenario": "arrange", "resume": False}, cfg)
        b = graph.invoke({"scenario": "arrange", "resume": False}, cfg)
        assert not a["error"] and not b["error"]
        assert a["outcome"] == b["outcome"] == "arranged"
        assert a["case_id"] != b["case_id"]
        assert a["run_id"] != b["run_id"]
        assert len(a["messages"]) == len(b["messages"])
        assert len(b["evidence"]["exchanges"]) == 1


def test_persisted_error_cannot_display_old_success(tmp_path):
    with sqlite_checkpointer(tmp_path / "threads.db") as saver:
        graph = flow.build_offline_graph(saver)
        cfg = {"configurable": {"thread_id": "bad-second"}}
        first = graph.invoke({"case_id": "EXPLICIT-1"}, cfg)
        assert first["outcome"] == "arranged"
        failed = graph.invoke({"case_id": "EXPLICIT-1", "resume": False}, cfg)
        assert failed["error"]
        assert failed["reply"] is None and failed["outcome"] is None
        assert failed["evidence"]["diagnostic_only"]


@pytest.mark.parametrize("case_id", ["../escape", "/tmp/escape", "C:\\escape", "..", "a/b"])
def test_case_paths_stay_inside_root(case_id):
    out = flow.build_offline_graph().invoke({"case_id": case_id})
    assert out["error"]
    assert out["reply"] is None


@requires_symlink
def test_symlink_escape_is_rejected(tmp_path):
    root = Path(flow._studio_root()); root.mkdir()
    outside = tmp_path / "outside"; outside.mkdir()
    (root / "LINK").symlink_to(outside, target_is_directory=True)
    out = flow.build_offline_graph().invoke({"case_id": "LINK"})
    assert "escapes" in out["error"]
    assert not (outside / "shop.db").exists()


def test_missing_live_config_routes_to_error_without_db_or_reply():
    out = flow.build_live_graph().invoke({"budget": 2})
    assert "SWAPDESK_MODEL" in out["error"]
    assert out["reply"] is None and out["outcome"] is None
    assert not Path(flow._studio_root()).exists()


@pytest.mark.parametrize("budget", [True, False, 0, -1, "2", 1.5, None])
def test_invalid_budget_is_rejected(budget):
    out = flow.build_live_graph().invoke({"budget": budget})
    assert "budget" in out["error"]
    assert out["reply"] is None


def test_composed_input_contains_case_run_and_consent():
    out = flow.build_offline_graph().invoke({"case_id": "CONSENT", "run_id": "RUN-C", "consent_size": "42"})
    text = out["messages"][0].content
    assert "case_id: CONSENT" in text and "run_id: RUN-C" in text
    assert "accepts size 42" in text


def test_no_terminal_state_does_not_invent_escalation(monkeypatch):
    monkeypatch.setattr(flow, "script_for", lambda *a: [AIMessage(content="done")])
    out = flow.build_offline_graph().invoke({})
    assert "without a persisted terminal" in out["error"]
    assert out["reply"] is None and out["outcome"] is None


def test_interrupted_subgraph_resumes_pending_execution(tmp_path):
    with sqlite_checkpointer(tmp_path / "threads.db") as saver:
        graph = flow.build_offline_graph(saver, interrupt_after_tools=True)
        cfg = {"configurable": {"thread_id": "interrupted"}}
        out = graph.invoke({"case_id": "INTERRUPTED", "run_id": "RUN-I"}, cfg)
        assert out.get("outcome") is None
        assert graph.get_state(cfg).next == ("agent",)
        for _ in range(8):
            if not graph.get_state(cfg).next:
                break
            out = graph.invoke(None, cfg)
        assert out["outcome"] == "arranged", out.get("error")
        calls = [c["name"] for m in out["messages"] if isinstance(m, AIMessage) for c in m.tool_calls]
        assert calls.count("reserve_replacement") == 1
        assert calls.count("get_order") == 1
        assert len(out["evidence"]["exchanges"]) == 1


def test_wrong_run_cannot_resume(tmp_path):
    with sqlite_checkpointer(tmp_path / "threads.db") as saver:
        graph = flow.build_offline_graph(saver)
        cfg = {"configurable": {"thread_id": "resume"}}
        graph.invoke({"case_id": "RESUME", "run_id": "RUN-A"}, cfg)
        out = graph.invoke({"case_id": "RESUME", "run_id": "RUN-B", "resume": True}, cfg)
        assert "original run_id" in out["error"]
        assert out["reply"] is None


def test_atomic_budget_reservations(tmp_path):
    state = flow.prepare({"case_id": "BUDGET", "budget": 2})
    def claim(_):
        try:
            return flow._spent_on_disk(state, 1)
        except BudgetExceeded:
            return "blocked"
    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(claim, range(6)))
    assert results.count("blocked") == 4
    assert flow._spent_on_disk(state) == 2


def response():
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(text="ok")]))])


def model(monkeypatch, budget=1):
    monkeypatch.setenv("GEMINI_API_KEY", "unit-test-only-not-a-real-key")
    return BudgetedChatModel(model="gemini-test").set_budget(budget)


def test_sync_transport_and_sdk_retry_settings(monkeypatch):
    m = model(monkeypatch)
    calls = []
    def generate(**kw):
        calls.append(kw)
        assert kw["config"].http_options.retry_options.attempts == 1
        return response()
    monkeypatch.setattr(m.client.models, "generate_content", generate)
    m.invoke([HumanMessage(content="hello")], max_retries=99, http_options={"retry_options": {"attempts": 99}})
    with pytest.raises(BudgetExceeded):
        m.invoke([HumanMessage(content="again")])
    assert len(calls) == m.spent == 1


def test_stream_transport_counts_and_caps(monkeypatch):
    m = model(monkeypatch); calls = []
    def generate(**kw):
        calls.append(kw)
        assert kw["config"].http_options.retry_options.attempts == 1
        return iter([response()])
    monkeypatch.setattr(m.client.models, "generate_content_stream", generate)
    list(m.stream([HumanMessage(content="hello")]))
    with pytest.raises(BudgetExceeded):
        list(m.stream([HumanMessage(content="again")]))
    assert len(calls) == m.spent == 1


def test_async_transport_counts_and_caps(monkeypatch):
    m = model(monkeypatch); calls = []
    async def generate(**kw):
        calls.append(kw)
        assert kw["config"].http_options.retry_options.attempts == 1
        return response()
    monkeypatch.setattr(m.async_client.models, "generate_content", generate)
    async def run():
        await m.ainvoke([HumanMessage(content="hello")])
        with pytest.raises(BudgetExceeded):
            await m.ainvoke([HumanMessage(content="again")])
    asyncio.run(run())
    assert len(calls) == m.spent == 1


def test_async_stream_transport_counts_and_caps(monkeypatch):
    m = model(monkeypatch); calls = []
    async def chunks():
        yield response()
    async def generate(**kw):
        calls.append(kw)
        assert kw["config"].http_options.retry_options.attempts == 1
        return chunks()
    monkeypatch.setattr(m.async_client.models, "generate_content_stream", generate)
    async def run():
        async for _ in m.astream([HumanMessage(content="hello")]):
            pass
        with pytest.raises(BudgetExceeded):
            async for _ in m.astream([HumanMessage(content="again")]):
                pass
    asyncio.run(run())
    assert len(calls) == m.spent == 1


def test_failed_attempt_stays_spent(monkeypatch):
    m = model(monkeypatch); calls = []
    def generate(**kw):
        calls.append(kw)
        raise RuntimeError("mock transport failure")
    monkeypatch.setattr(m.client.models, "generate_content", generate)
    with pytest.raises(RuntimeError):
        m.invoke([HumanMessage(content="hello")])
    with pytest.raises(BudgetExceeded):
        m.invoke([HumanMessage(content="again")])
    assert len(calls) == m.spent == 1


def test_live_exhaustion_no_reply_and_cumulative_resume_budget(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "unit-test-only-not-a-real-key")
    monkeypatch.setenv("SWAPDESK_MODEL", "gemini-test")
    from langchain_core.outputs import ChatGeneration, ChatResult
    def generate(self, *a, **kw):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{"id": "read", "name": "get_return_policy", "args": {}, "type": "tool_call"}]))])
    monkeypatch.setattr(ChatGoogleGenerativeAI, "_generate", generate)
    with sqlite_checkpointer(tmp_path / "threads.db") as saver:
        graph = flow.build_live_graph(saver)
        cfg = {"configurable": {"thread_id": "capped-live"}}
        out = graph.invoke({"case_id": "LIVE-CAP", "run_id": "RUN-L", "budget": 1}, cfg)
        assert "budget exhausted" in out["error"]
        assert out["requests_spent"] == 1
        assert out["reply"] is None and out["outcome"] is None
        assert out["evidence"]["diagnostic_only"]
        resumed = graph.invoke({"resume": True, "case_id": "LIVE-CAP", "run_id": "RUN-L", "budget": 1}, cfg)
        assert "budget exhausted" in resumed["error"]
        assert resumed["requests_spent"] == 1


def test_offline_async_graph_uses_real_tools_without_provider(monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("provider model constructed in offline mode")
    monkeypatch.setattr(flow, "BudgetedChatModel", forbidden)
    out = asyncio.run(flow.build_offline_graph().ainvoke({"scenario": "arrange"}))
    assert out["outcome"] == "arranged", out.get("error")
    assert any(isinstance(m, ToolMessage) and m.name == "reserve_replacement" for m in out["messages"])
