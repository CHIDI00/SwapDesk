"""Agent loop proofs: deterministic scripted model, no API spend."""

import itertools
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import AIMessage

from swapdesk import faults
from swapdesk.agent.graph import (
    AgentContext,
    build_model,
    derive_outcome,
    run_agent,
    sqlite_checkpointer,
)
from swapdesk.agent.scripted import ScriptedChatModel, call as _call
from swapdesk.db import connect, init_db
from swapdesk.fixtures import load_fixtures
from swapdesk import telemetry


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    monkeypatch.setenv("SWAPDESK_TELEMETRY_ENV", "0")
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
    faults.clear()
    yield
    faults.clear()


@pytest.fixture()
def shop(tmp_path):
    db_path = tmp_path / "shop.db"
    conn = connect(db_path)
    init_db(conn)
    load_fixtures(conn)
    conn.close()
    return db_path


def _ctx(db_path, case="AG-1", run="RUN-AG1", message="", consent=None):
    return AgentContext(db_path=db_path, case_id=case, run_id=run,
                        message=message, consent_size=consent)


def _stock(db_path, sku, size):
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT on_hand, held FROM stock WHERE sku = ? "
                           "AND size = ?", (sku, size)).fetchone()
        return (row["on_hand"], row["held"])
    finally:
        conn.close()


def test_agent_arranges_from_observed_results(shop):
    eid = "EXC-ITEM-01-1"
    model = ScriptedChatModel([
        _call("get_order", {"order_id": "ORD-1001"}),
        _call("find_exchange_stock",
              {"sku": "AIRFLOW-RUNNER", "size": "42"}),
        _call("reserve_replacement",
              {"order_id": "ORD-1001", "order_item_id": "ITEM-01",
               "size": "42"}),
        _call("create_return", {"exchange_id": eid}),
        _call("create_label", {"exchange_id": eid}),
        _call("finalize_arranged", {"exchange_id": eid}),
        AIMessage(content="Reply: tracking TRK-FAKE-999, all set!"),
    ])
    out = run_agent(_ctx(shop, message="size 42 please, order ORD-1001"),
                    model=model)
    assert out["outcome"] == "arranged"
    assert out["exchange_id"] == eid
    assert f"TRK-MOCK-{eid}" in out["reply"]
    assert "TRK-FAKE-999" not in out["reply"]
    assert _stock(shop, "AIRFLOW-RUNNER", "42") == (9, 0)


def test_agent_denies_final_sale(shop):
    model = ScriptedChatModel([
        _call("get_order", {"order_id": "ORD-1001"}),
        _call("reserve_replacement",
              {"order_id": "ORD-1001", "order_item_id": "ITEM-02",
               "size": "40"}),
        _call("record_denial", {"reason": "sold as final sale"}),
        AIMessage(content="sorry, no can do"),
    ])
    out = run_agent(_ctx(shop, case="AG-2", run="RUN-AG2",
                         message="exchange ITEM-02"), model=model)
    assert out["outcome"] == "denial"
    assert out["reply"] == "Exchange denied: sold as final sale"
    conn = connect(shop)
    try:
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM exchanges").fetchone()["n"] == 0
    finally:
        conn.close()


def test_agent_clarifies_unknown_item(shop):
    model = ScriptedChatModel([
        _call("get_order", {"order_id": "ORD-1001"}),
        _call("record_clarification",
              {"question": "provide your order number and item id"}),
        AIMessage(content="need more info"),
    ])
    out = run_agent(_ctx(shop, case="AG-3", run="RUN-AG3",
                         message="exchange my shoes"), model=model)
    assert out["outcome"] == "clarification"
    assert "provide your order number" in out["reply"]
    assert _stock(shop, "AIRFLOW-RUNNER", "42") == (10, 0)


def test_agent_escalates_with_release(shop):
    eid = "EXC-ITEM-01-1"
    model = ScriptedChatModel([
        _call("get_order", {"order_id": "ORD-1001"}),
        _call("reserve_replacement",
              {"order_id": "ORD-1001", "order_item_id": "ITEM-01",
               "size": "42"}),
        _call("escalate_to_human",
              {"exchange_id": eid, "reason": "customer asked for a human"}),
        AIMessage(content="handing off"),
    ])
    out = run_agent(_ctx(shop, case="AG-4", run="RUN-AG4",
                         message="I want a human"), model=model)
    assert out["outcome"] == "escalation"
    assert "customer asked for a human" in out["reply"]
    assert "released" in out["reply"]
    assert _stock(shop, "AIRFLOW-RUNNER", "42") == (10, 0)


def test_agent_recovers_crash_via_operation_status(shop):
    from swapdesk.agent.tools import ToolContext, build_tools

    ctx = ToolContext(db_path=shop, case_id="AG-5", run_id="RUN-AG5")
    (reserve,) = [t for t in build_tools(ctx)
                  if t.name == "reserve_replacement"]
    (status_of,) = [t for t in build_tools(ctx)
                    if t.name == "get_operation_status"]
    faults.inject("AG-5:RUN-AG5:reserve", "crash")
    first = json.loads(reserve.invoke(
        {"order_id": "ORD-1002", "order_item_id": "ITEM-03", "size": "42"}))
    assert first["ok"] is False
    assert first["retry_same_key"] is True
    op_key = first["op_key"]
    seen = json.loads(status_of.invoke({"op_key": op_key}))
    assert seen["operation"]["status"] == "committed"
    second = json.loads(reserve.invoke(
        {"order_id": "ORD-1002", "order_item_id": "ITEM-03", "size": "42"}))
    assert second["ok"] is True
    assert second["exchange_id"] == seen["operation"]["result"]["exchange_id"]
    assert _stock(shop, "TRAIL-BEAST", "42") == (1, 1)


def test_agent_loop_is_bounded(shop):
    from langgraph.errors import GraphRecursionError

    model = ScriptedChatModel(
        _call("get_return_policy", {}, cid=f"loop-{n}")
        for n in itertools.count())
    with pytest.raises(GraphRecursionError):
        run_agent(_ctx(shop, case="AG-6", run="RUN-AG6",
                       message="loop forever"), model=model,
                  max_tool_calls=3)


def test_agent_resumes_thread_without_double_effects(shop, tmp_path):
    model = ScriptedChatModel([
        _call("get_order", {"order_id": "ORD-1001"}),
        AIMessage(content="noted"),
        AIMessage(content="still here"),
    ])
    with sqlite_checkpointer(tmp_path / "ckpt.db") as saver:
        first = run_agent(_ctx(shop, case="AG-7", run="RUN-AG7",
                               message="hello"), model=model,
                          checkpointer=saver)
        second = run_agent(_ctx(shop, case="AG-7", run="RUN-AG7",
                                message="hello again"), model=model,
                           checkpointer=saver)
    assert "hello again" in second["messages"][-2].content
    assert len(second["messages"]) > len(first["messages"])
    # The resumed run wrote nothing: no case progress at all.
    assert second["outcome"] == "escalation"
    assert "no progress" in second["reply"]
    assert _stock(shop, "AIRFLOW-RUNNER", "42") == (10, 0)


def test_build_model_uses_user_default(monkeypatch):
    from langchain_google_genai import ChatGoogleGenerativeAI

    monkeypatch.delenv("SWAPDESK_MODEL", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    client = build_model()
    assert isinstance(client, ChatGoogleGenerativeAI)
    assert client.model == "gemini-3.8-flash"


def test_build_model_accepts_env_id(monkeypatch):
    from langchain_google_genai import ChatGoogleGenerativeAI

    monkeypatch.setenv("SWAPDESK_MODEL", "gemini-test-id")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    assert isinstance(build_model(), ChatGoogleGenerativeAI)


def test_telemetry_local_without_key():
    assert telemetry.init_telemetry(workflow_name="swapdesk-test") is False
    assert telemetry.is_exporting() is False
    telemetry.flush()


def test_dotenv_loader_names_only(tmp_path, monkeypatch):
    monkeypatch.delenv("SWAPDESK_TELEMETRY_ENV", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("FAKE_SLICE4_KEY=abc123\n# comment\nEMPTY=\n",
                        encoding="utf-8")
    telemetry.load_dotenv(tmp_path)
    assert os.environ["FAKE_SLICE4_KEY"] == "abc123"
    del os.environ["FAKE_SLICE4_KEY"]


def test_neatlogs_doctor_local_passes():
    import json as _json
    import subprocess

    proc = subprocess.run(
        [sys.executable, "-m", "neatlogs", "doctor", "--local", "--json"],
        capture_output=True, text=True, cwd=str(
            Path(__file__).resolve().parent.parent))
    doc = _json.loads(proc.stdout)
    assert doc["first_failure"] is None
    assert any(c["status"] == "pass" for c in doc["checks"])
