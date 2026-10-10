"""Studio verification proofs: isolated, offline-first, budget-guarded."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from swapdesk import faults
from swapdesk.agent import studio_flow
from swapdesk.agent.capped import BudgetExceeded, BudgetedChatModel


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch, tmp_path):
    monkeypatch.setenv("SWAPDESK_TELEMETRY_ENV", "0")
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
    monkeypatch.setenv("SWAPDESK_STUDIO_ROOT", str(tmp_path / "studio"))
    faults.clear()
    yield
    faults.clear()


@pytest.fixture()
def threads(tmp_path):
    from swapdesk.agent.graph import sqlite_checkpointer

    with sqlite_checkpointer(tmp_path / "threads.db") as saver:
        yield saver


def _offline():
    return studio_flow.build_offline_graph()


def _live():
    return studio_flow.build_live_graph()


def _tid(case, run="RUN-1"):
    return {"configurable": {"thread_id": f"{case}:{run}"},
            "recursion_limit": 50}


def _no_live(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("live model path touched in offline mode")

    monkeypatch.setattr(studio_flow, "BudgetedChatModel", _boom)
    import langchain_google_genai

    monkeypatch.setattr(langchain_google_genai, "ChatGoogleGenerativeAI",
                        _boom)


def _committed_ops(db_path, case_id, op_type):
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM operations WHERE case_id = ? "
            "AND op_type = ? AND status = 'committed'",
            (case_id, op_type)).fetchone()[0]
    finally:
        conn.close()


def test_offline_arrange_shows_tool_execution(threads, monkeypatch):
    _no_live(monkeypatch)
    graph = _offline()
    out = graph.invoke({"scenario": "arrange", "case_id": "DEMO-T1"},
                       _tid("DEMO-T1"))
    assert out["outcome"] == "arranged", out.get("error")
    assert "TRK-MOCK-EXC-ITEM-01-1" in out["reply"]
    assert "wiring verification" in out["evidence"]["label"]
    calls = [step["calls"] for step in out["agent_trace"]
             if step["role"] == "model" and "calls" in step]
    names = [n for group in calls for n, _ in group]
    for tool in ("get_order", "reserve_replacement", "create_return",
                 "create_label", "finalize_arranged"):
        assert tool in names, names
    assert len(out["evidence"]["exchanges"]) == 1
    assert _committed_ops(out["db_path"], "DEMO-T1", "reserve_replacement") == 1


def test_offline_deny_writes_nothing(threads, monkeypatch):
    _no_live(monkeypatch)
    out = _offline().invoke({"scenario": "deny", "case_id": "DEMO-T2"},
                            _tid("DEMO-T2"))
    assert out["outcome"] == "denial", out.get("error")
    assert out["reply"] == "Exchange denied: sold as final sale"
    assert out["evidence"]["exchanges"] == []
    assert _committed_ops(out["db_path"], "DEMO-T2", "reserve_replacement") == 0


def test_offline_recover_reuses_same_key(threads, monkeypatch):
    _no_live(monkeypatch)
    out = _offline().invoke({"scenario": "recover", "case_id": "DEMO-T3"},
                            _tid("DEMO-T3"))
    assert out["outcome"] == "arranged", out.get("error")
    assert out["exchange_id"] == "EXC-ITEM-04-1"
    assert _committed_ops(out["db_path"], "DEMO-T3",
                          "reserve_replacement") == 1
    assert _committed_ops(out["db_path"], "DEMO-T3", "create_label") == 1


def test_case_isolation_never_resets_silently(threads):
    graph = _offline()
    first = graph.invoke({"scenario": "arrange", "case_id": "DEMO-T4"},
                         _tid("DEMO-T4"))
    assert first["outcome"] == "arranged"
    second = graph.invoke({"scenario": "arrange", "case_id": "DEMO-T4"},
                          _tid("DEMO-T4"))
    assert "already active" in (second.get("error") or "")
    assert second.get("outcome") is None


def test_explicit_resume_preserves_case(threads):
    graph = studio_flow.build_offline_graph(checkpointer=threads)
    first = graph.invoke({"scenario": "arrange", "case_id": "DEMO-T5"},
                         _tid("DEMO-T5"))
    assert first["outcome"] == "arranged"
    second = graph.invoke({"scenario": "arrange", "case_id": "DEMO-T5",
                           "resume": True, "message": "status check"},
                          _tid("DEMO-T5"))
    assert second["outcome"] == "arranged", second.get("error")
    assert second["exchange_id"] == first["exchange_id"]
    assert _committed_ops(second["db_path"], "DEMO-T5",
                          "reserve_replacement") == 1
    checkpoints = list(threads.list({"configurable": {"thread_id":
                                                      "DEMO-T5:RUN-1"}}))
    assert len(checkpoints) >= 2


def test_live_without_budget_makes_no_calls(threads, monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("model built without a budget")

    monkeypatch.setattr(studio_flow, "BudgetedChatModel", _boom)
    out = _live().invoke({"message": "hello"}, _tid("DEMO-T6"))
    assert "budget" in (out.get("error") or "")


def test_live_without_config_fails_clearly(threads, monkeypatch):
    monkeypatch.delenv("SWAPDESK_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    out = _live().invoke({"message": "hello", "budget": 3,
                          "case_id": "DEMO-T7"}, _tid("DEMO-T7"))
    assert "SWAPDESK_MODEL" in (out.get("error") or "")


def test_budget_cap_refuses_before_any_request(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    model = BudgetedChatModel(model="gemini-test-id").set_budget(0)
    with pytest.raises(BudgetExceeded):
        model._generate([{"role": "user", "content": "hi"}])
    assert model.spent == 0


def test_budget_counts_requests_then_caps(monkeypatch):
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")

    def _stub(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(
            message=AIMessage(content="ok"))])

    monkeypatch.setattr(
        "langchain_google_genai.ChatGoogleGenerativeAI._generate", _stub)
    model = BudgetedChatModel(model="gemini-test-id").set_budget(2)
    model._generate([])
    model._generate([])
    assert model.spent == 2
    with pytest.raises(BudgetExceeded):
        model._generate([])


def test_demo_never_touches_benchmark_holdouts():
    root = Path(__file__).resolve().parent.parent
    doc = json.loads((root / "eval" / "cases_v1.json").read_text())
    frozen_ids = {c["case_id"] for c in doc["cases"]}
    holdouts = {c["case_id"] for c in doc["cases"] if c.get("holdout")}
    assert len(holdouts) == 8
    for scenario in studio_flow.SCENARIOS:
        assert studio_flow.default_case_id(scenario) not in frozen_ids
    for name in ("studio_flow.py", "scripted.py"):
        text = (root / "src" / "swapdesk" / "agent" / name).read_text()
        assert "cases_v1" not in text


def test_studio_entrypoints_and_config():
    # Local import: the hermetic fixture must set SWAPDESK_STUDIO_ROOT
    # before this module-level saver is created.
    from swapdesk.agent import studio

    assert hasattr(studio, "offline_graph")
    assert hasattr(studio, "live_graph")
    root = Path(__file__).resolve().parent.parent
    cfg = json.loads((root / "langgraph.json").read_text())
    assert set(cfg["graphs"]) == {"swapdesk_offline", "swapdesk_live"}
