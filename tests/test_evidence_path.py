"""Evidence-path regression: persisted state -> run_agent -> _run_log -> checker.

Deterministic scripted model only; zero paid model calls. Proves
runner/harness correctness (evidence plumbing), not model reasoning.
Covers denial, clarification, and escalation.
"""

import sys
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.baseline import _run_log  # noqa: E402
from eval.harness import fresh_db, snapshot  # noqa: E402
from swapdesk import faults  # noqa: E402
from swapdesk.agent.graph import AgentContext, run_agent  # noqa: E402
from swapdesk.agent.scripted import ScriptedChatModel, call as _call  # noqa: E402
from swapdesk.checker import check_run  # noqa: E402
from swapdesk.db import connect, init_db  # noqa: E402
from swapdesk.fixtures import load_fixtures  # noqa: E402
from swapdesk import telemetry  # noqa: E402


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    monkeypatch.setenv("SWAPDESK_TELEMETRY_ENV", "0")
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
    faults.clear()
    yield
    faults.clear()


def _shop(tmp_path):
    db_path = tmp_path / "shop.db"
    conn = connect(db_path)
    init_db(conn)
    load_fixtures(conn)
    conn.close()
    return db_path


def test_denial_evidence_reaches_checker(tmp_path):
    shop = _shop(tmp_path)
    baseline = snapshot(shop)
    model = ScriptedChatModel([
        _call("get_order", {"order_id": "ORD-1001"}),
        _call("reserve_replacement",
              {"order_id": "ORD-1001", "order_item_id": "ITEM-02",
               "size": "40"}),
        _call("record_denial", {"reason": "sold as final sale"}),
        AIMessage(content="sorry"),
    ])
    ctx = AgentContext(db_path=shop, case_id="EV-DENY", run_id="RUN-1",
                       message="exchange ITEM-02")
    out = run_agent(ctx, model=model)
    assert out["outcome"] == "denial"
    # Runner returns the persisted reason (run_agent fix).
    assert out["data"]["reason"] == "sold as final sale"
    log = _run_log(shop, "EV-DENY", out)
    # Harness preserves it for the checker (_run_log fix).
    assert log["reason"] == "sold as final sale"
    case = {"case_id": "EV-DENY", "outcome": "denied",
            "order_id": "ORD-1001", "order_item_id": "ITEM-02",
            "reason_contains": "final sale"}
    check = check_run(shop, case, log, baseline)
    assert not any("expected message" in f for f in check.failures), \
        check.failures
    assert check.passed, check.failures


def test_clarification_evidence_reaches_checker(tmp_path):
    shop = _shop(tmp_path)
    baseline = snapshot(shop)
    model = ScriptedChatModel([
        _call("get_order", {"order_id": "ORD-1001"}),
        _call("record_clarification",
              {"question": "provide your order number and item id"}),
        AIMessage(content="need info"),
    ])
    ctx = AgentContext(db_path=shop, case_id="EV-CLAR", run_id="RUN-1",
                       message="exchange my shoes")
    out = run_agent(ctx, model=model)
    assert out["outcome"] == "clarification"
    assert out["data"]["question"] == \
        "provide your order number and item id"
    log = _run_log(shop, "EV-CLAR", out)
    assert log["question"] == "provide your order number and item id"
    case = {"case_id": "EV-CLAR", "outcome": "clarification",
            "order_id": "ORD-1001", "order_item_id": "ITEM-99",
            "question_contains": "order number"}
    check = check_run(shop, case, log, baseline)
    assert not any("expected message" in f for f in check.failures), \
        check.failures
    assert check.passed, check.failures


def test_escalation_evidence_reaches_checker(tmp_path):
    shop = _shop(tmp_path)
    baseline = snapshot(shop)
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
    ctx = AgentContext(db_path=shop, case_id="EV-ESC", run_id="RUN-1",
                       message="I want a human")
    out = run_agent(ctx, model=model)
    assert out["outcome"] == "escalation"
    assert out["exchange_id"] == eid
    # Persisted escalation reason reaches the runner result.
    assert "customer asked for a human" in out["data"]["reason"]
    log = _run_log(shop, "EV-ESC", out)
    assert log["reason"] == out["data"]["reason"]
    case = {"case_id": "EV-ESC", "outcome": "escalated",
            "order_id": "ORD-1001", "order_item_id": "ITEM-01",
            "reason_contains": "customer asked for a human"}
    check = check_run(shop, case, log, baseline)
    assert not any("expected escalation reason" in f
                   for f in check.failures), check.failures
    assert check.passed, check.failures
