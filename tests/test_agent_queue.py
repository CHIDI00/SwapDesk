"""Reconciled agent-queue proofs: HTTP accept -> worker -> agent service path.

Offline only: scripted models are injected explicitly, zero paid calls,
zero network. Each test drives the same production route
(service.submit_agent_ticket per claimed run). Covers arranged, denial,
clarification/continuation, duplicate submission, concurrent claiming,
terminal resubmission without a new model call, execution failure,
timeout recovery, request-budget exhaustion, and the narrowed stock
guard. Checker untouched.
"""

import itertools
import os
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from swapdesk import faults  # noqa: E402
from swapdesk import queue as _queue  # noqa: E402
from swapdesk import worker as _worker  # noqa: E402
from swapdesk.agent.scripted import ScriptedChatModel, call as _call  # noqa: E402
from swapdesk.api import app  # noqa: E402
from swapdesk.db import connect  # noqa: E402


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch, tmp_path):
    monkeypatch.setenv("SWAPDESK_TELEMETRY_ENV", "0")
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("SWAPDESK_MODEL", raising=False)
    monkeypatch.delenv("SWAPDESK_ENABLE_DEMO_FAULTS", raising=False)
    monkeypatch.setenv("SWAPDESK_DB", str(tmp_path / "queue.db"))
    faults.clear()
    yield
    faults.clear()


@pytest.fixture()
def client():
    return TestClient(app)


def _db():
    return os.environ["SWAPDESK_DB"]


def _drain(factory, **kwargs):
    n = 0
    while _worker.drain_once(_db(), model_factory=factory, **kwargs):
        n += 1
        if n > 10:
            raise AssertionError("worker did not go idle")
    return n


def _arrange_model():
    eid = "EXC-ITEM-01-1"
    return ScriptedChatModel([
        _call("get_order", {"order_id": "ORD-1001"}),
        _call("find_exchange_stock",
              {"sku": "AIRFLOW-RUNNER", "size": "42"}),
        _call("reserve_replacement",
              {"order_id": "ORD-1001", "order_item_id": "ITEM-01",
               "size": "42"}),
        _call("create_return", {"exchange_id": eid}),
        _call("create_label", {"exchange_id": eid}),
        _call("finalize_arranged", {"exchange_id": eid}),
        AIMessage(content="arranged"),
    ])


def _count(sql, args=()):
    conn = connect(_db())
    try:
        return conn.execute(sql, args).fetchone()[0]
    finally:
        conn.close()


def test_arranged_through_queue(client):
    created = client.post("/v1/agent/tickets", json={
        "message": "Please exchange ITEM-01 on order ORD-1001 for size 42",
        "order_id": "ORD-1001", "order_item_id": "ITEM-01", "size": "42"})
    assert created.status_code == 202, created.text
    body = created.json()
    assert body["execution_status"] == "queued"
    assert body["status_url"].endswith(body["case_id"])
    assert "outcome" not in body
    case_id = body["case_id"]

    queued = client.get(f"/v1/agent/cases/{case_id}").json()
    assert queued["execution_status"] == "queued"
    assert queued["outcome"] is None
    assert queued["trace_id"] is None

    assert _drain(_arrange_model) == 1
    status = client.get(f"/v1/agent/cases/{case_id}").json()
    assert status["execution_status"] == "completed"
    assert status["outcome"] == "arranged"
    assert status["exchange_id"] == "EXC-ITEM-01-1"
    assert "TRK-MOCK-EXC-ITEM-01-1" in status["reply"]
    assert status["trace_id"] == f"{case_id}:RUN-1"

    timeline = client.get(f"/v1/agent/cases/{case_id}/timeline").json()
    assert [e["event"] for e in timeline] == [
        "reserved", "return_created", "label_created", "arranged"]
    assert all(e["run_id"] == "RUN-1" for e in timeline)
    assert _count("SELECT COUNT(*) AS n FROM exchanges") == 1
    assert _count("SELECT COUNT(*) AS n FROM labels") == 1


def test_denial_writes_no_fulfillment(client):
    created = client.post("/v1/agent/tickets", json={
        "message": "Please exchange ITEM-02 for size 40",
        "order_id": "ORD-1001", "order_item_id": "ITEM-02", "size": "40"})
    assert created.status_code == 202
    case_id = created.json()["case_id"]
    model = ScriptedChatModel([
        _call("get_order", {"order_id": "ORD-1001"}),
        _call("reserve_replacement",
              {"order_id": "ORD-1001", "order_item_id": "ITEM-02",
               "size": "40"}),
        _call("record_denial", {"reason": "sold as final sale"}),
        AIMessage(content="denied"),
    ])
    _drain(lambda: model)
    status = client.get(f"/v1/agent/cases/{case_id}").json()
    assert status["execution_status"] == "completed"
    assert status["outcome"] == "denial"
    assert status["exchange_id"] is None
    assert client.get(f"/v1/agent/cases/{case_id}/timeline").json() == []
    assert _count("SELECT COUNT(*) AS n FROM exchanges") == 0


def test_clarification_continues_with_consent(client):
    first = client.post("/v1/agent/tickets", json={
        "message": "Need to exchange, not sure of the size",
        "order_id": "ORD-1005", "order_item_id": "ITEM-06", "size": "43"})
    assert first.status_code == 202
    case_id = first.json()["case_id"]
    clarify = ScriptedChatModel([
        _call("get_order", {"order_id": "ORD-1005"}),
        _call("find_exchange_stock",
              {"sku": "TRAIL-BEAST", "size": "43"}),
        _call("record_clarification",
              {"question": "size 43 is unavailable (only 0 unit(s) in "
                           "stock); reply with an alternative size or ask "
                           "for a human"}),
        AIMessage(content="need size choice"),
    ])
    _drain(lambda: clarify)
    waiting = client.get(f"/v1/agent/cases/{case_id}").json()
    assert waiting["execution_status"] == "waiting_input"
    assert waiting["outcome"] == "clarification"
    assert waiting["clarification"]

    cont = client.post(f"/v1/agent/cases/{case_id}/continue", json={
        "message": "42 is fine", "consent_size": "42"})
    assert cont.status_code == 202, cont.text
    assert cont.json()["run_id"] == "RUN-2"

    eid = "EXC-ITEM-06-1"
    arrange_alt = ScriptedChatModel([
        _call("get_order", {"order_id": "ORD-1005"}),
        _call("find_exchange_stock",
              {"sku": "TRAIL-BEAST", "size": "42"}),
        _call("reserve_replacement",
              {"order_id": "ORD-1005", "order_item_id": "ITEM-06",
               "size": "42", "requested_size": "43", "consent": True}),
        _call("create_return", {"exchange_id": eid}),
        _call("create_label", {"exchange_id": eid}),
        _call("finalize_arranged", {"exchange_id": eid}),
        AIMessage(content="arranged with consent"),
    ])
    _drain(lambda: arrange_alt)
    done = client.get(f"/v1/agent/cases/{case_id}").json()
    assert done["execution_status"] == "completed"
    assert done["outcome"] == "arranged"
    assert done["exchange_id"] == eid
    assert done["runs"] == ["RUN-1", "RUN-2"]
    assert _count("SELECT COUNT(*) AS n FROM exchanges") == 1


def test_duplicate_submission_returns_existing_case(client):
    payload = {"message": "exchange please",
               "order_id": "ORD-1001", "order_item_id": "ITEM-01",
               "size": "42", "idempotency_key": "storefront-1"}
    one = client.post("/v1/agent/tickets", json=payload)
    assert one.status_code == 202
    two = client.post("/v1/agent/tickets", json=payload)
    assert two.status_code == 202
    assert two.json()["duplicate"] is True
    assert two.json()["case_id"] == one.json()["case_id"]
    assert two.json()["run_id"] == "RUN-1"

    clash = dict(payload, size="43")
    assert client.post("/v1/agent/tickets", json=clash).status_code == 409

    _drain(_arrange_model)
    status = client.get(
        f"/v1/agent/cases/{one.json()['case_id']}").json()
    assert status["runs"] == ["RUN-1"]
    assert _count("SELECT COUNT(*) AS n FROM exchanges") == 1


def test_concurrent_continue_conflicts_then_claims_atomically(client):
    created = client.post("/v1/agent/tickets", json={"message": "help me"})
    case_id = created.json()["case_id"]
    assert client.post(f"/v1/agent/cases/{case_id}/continue",
                       json={"message": "nudge"}).status_code == 409
    other = client.post("/v1/agent/tickets",
                        json={"message": "second ticket"}).json()["case_id"]
    first_claim = _queue.claim_next_run(_db())
    second_claim = _queue.claim_next_run(_db())
    assert first_claim is not None and second_claim is not None
    assert {first_claim["case_id"], second_claim["case_id"]} == {
        case_id, other}
    third = _queue.claim_next_run(_db())
    assert third is None  # both cases have a running run: no double claim


def test_terminal_continue_uses_saved_result_without_model_call(client):
    created = client.post("/v1/agent/tickets", json={
        "message": "exchange ITEM-01 for 42",
        "order_id": "ORD-1001", "order_item_id": "ITEM-01", "size": "42"})
    case_id = created.json()["case_id"]
    calls = []

    def factory():
        calls.append(1)
        return _arrange_model()

    _drain(factory)
    assert len(calls) == 1
    again = client.post(f"/v1/agent/cases/{case_id}/continue",
                        json={"message": "hello again"})
    assert again.status_code == 200
    assert again.json()["continued"] is False
    assert again.json()["outcome"] == "arranged"
    assert len(calls) == 1  # no further model call happened
    assert _count("SELECT COUNT(*) AS n FROM exchanges") == 1


def test_missing_provider_fails_loudly_without_fallback(client):
    created = client.post("/v1/agent/tickets", json={
        "message": "exchange ITEM-01 for 42",
        "order_id": "ORD-1001", "order_item_id": "ITEM-01", "size": "42"})
    case_id = created.json()["case_id"]
    _drain(None)
    status = client.get(f"/v1/agent/cases/{case_id}").json()
    assert status["execution_status"] == "failed"
    assert status["outcome"] is None
    assert status["trace_id"] is None
    assert status["error"]
    assert _count("SELECT COUNT(*) AS n FROM exchanges") == 0


def test_label_timeout_recovers_same_key_single_label(client):
    created = client.post("/v1/agent/tickets", json={
        "message": "exchange ITEM-01 for 42",
        "order_id": "ORD-1001", "order_item_id": "ITEM-01", "size": "42",
        "case_id": "DEMO-AGENT-R1"})
    assert created.status_code == 202
    case_id = created.json()["case_id"]
    op_key = f"{case_id}:RUN-1:label"
    faults.inject(op_key, "timeout")
    eid = "EXC-ITEM-01-1"
    model = ScriptedChatModel([
        _call("get_order", {"order_id": "ORD-1001"}),
        _call("find_exchange_stock",
              {"sku": "AIRFLOW-RUNNER", "size": "42"}),
        _call("reserve_replacement",
              {"order_id": "ORD-1001", "order_item_id": "ITEM-01",
               "size": "42"}),
        _call("create_return", {"exchange_id": eid}),
        _call("create_label", {"exchange_id": eid}, cid="t1"),
        _call("get_operation_status", {"op_key": op_key}, cid="t2"),
        _call("create_label", {"exchange_id": eid}, cid="t3"),
        _call("finalize_arranged", {"exchange_id": eid}, cid="t4"),
        AIMessage(content="recovered"),
    ])
    _drain(lambda: model)
    status = client.get(f"/v1/agent/cases/{case_id}").json()
    assert status["outcome"] == "arranged", status
    assert _count("SELECT COUNT(*) AS n FROM labels") == 1
    assert _count(
        "SELECT COUNT(*) AS n FROM operations WHERE op_type = ? "
        "AND status = 'committed'", ("create_label",)) == 1


def test_request_budget_exhaustion_fails_run(client):
    created = client.post("/v1/agent/tickets", json={
        "message": "loop please", "order_id": "ORD-1001",
        "order_item_id": "ITEM-01", "size": "42"})
    case_id = created.json()["case_id"]
    looping = ScriptedChatModel(
        _call("get_return_policy", {}, cid=f"loop-{n}")
        for n in itertools.count())
    _drain(lambda: looping, max_requests=2)
    status = client.get(f"/v1/agent/cases/{case_id}").json()
    assert status["execution_status"] == "failed"
    assert "budget" in (status["error"] or "").lower()
    assert _count("SELECT COUNT(*) AS n FROM exchanges") == 0


def test_execution_timeout_records_failure_without_retry(client):
    class _Hanging(ScriptedChatModel):
        def _generate(self, messages, stop=None, run_manager=None,
                      **kwargs):
            time.sleep(30)
            return super()._generate(
                messages, stop=stop, run_manager=run_manager, **kwargs)

    created = client.post("/v1/agent/tickets",
                          json={"message": "take your time"})
    case_id = created.json()["case_id"]
    _drain(lambda: _Hanging([AIMessage(content="late")]), timeout_s=1)
    status = client.get(f"/v1/agent/cases/{case_id}").json()
    assert status["execution_status"] == "failed"
    assert "timed out" in (status["error"] or "")
    assert _drain(lambda: _Hanging([AIMessage(content="late")]),
                  timeout_s=1) == 0  # nothing requeued


def test_interrupted_runs_fail_without_replay(client):
    created = client.post("/v1/agent/tickets", json={"message": "help me"})
    case_id = created.json()["case_id"]
    conn = connect(_db())
    try:
        conn.execute("UPDATE runs SET state = 'running' WHERE case_id = ?",
                     (case_id,))
        conn.commit()
    finally:
        conn.close()
    assert _queue.mark_interrupted_failed(_db(), "test-interrupt") == 1
    assert client.get(
        f"/v1/agent/cases/{case_id}").json()["execution_status"] == "failed"
    cont = client.post(f"/v1/agent/cases/{case_id}/continue",
                       json={"message": "help me",
                             "order_id": "ORD-1001",
                             "order_item_id": "ITEM-01", "size": "42"})
    assert cont.status_code == 202
    assert cont.json()["run_id"] == "RUN-2"


def test_stock_guard_rejects_only_unsupported_stock_claims():
    import json as _json

    from swapdesk.agent.tools import ToolContext, build_tools
    from swapdesk.db import connect as _connect
    from swapdesk.db import init_db
    from swapdesk.fixtures import load_fixtures

    db = Path(_db()).parent / "guard.db"
    conn = _connect(db)
    init_db(conn)
    load_fixtures(conn)
    conn.close()
    ctx = ToolContext(
        db_path=db, case_id="AG-GUARD", run_id="RUN-1",
        order_id="ORD-1002", order_item_id="ITEM-03",
        requested_size="42", qty=1)
    clarify = next(t for t in build_tools(ctx)
                   if t.name == "record_clarification")
    denied = _json.loads(clarify.invoke({
        "question": "Size 42 is out of stock. Any alternative?"}))
    assert denied["ok"] is False
    assert "1 unit(s) available" in denied["error"]
    allowed = _json.loads(clarify.invoke({
        "question": "Which delivery address should the label use?"}))
    assert allowed["ok"] is True


def test_validation_and_unknown_case(client):
    assert client.post("/v1/agent/tickets",
                       json={"message": "   "}).status_code == 422
    assert client.get("/v1/agent/cases/CASE-NOPE").status_code == 404
    assert client.get("/v1/agent/cases/CASE-NOPE/timeline").status_code == 404
    assert client.post("/v1/agent/cases/CASE-NOPE/continue",
                       json={"message": "hi"}).status_code == 404
    vague = client.post("/v1/agent/tickets", json={"message": "help me"})
    assert vague.status_code == 202
    assert client.post(
        f"/v1/agent/cases/{vague.json()['case_id']}/continue",
        json={}).status_code in (409, 422)
