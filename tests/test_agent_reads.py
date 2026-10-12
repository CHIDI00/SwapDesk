"""Read-path acceptance: lists, inventory, readiness, supervision.

Network-free and model-free except where a scripted double drives the
same worker path (zero paid calls). Repeated reads must cause no
business mutations and no model calls.
"""

import base64
import json
import os
import sys
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
    monkeypatch.delenv("SWAPDESK_ENABLE_DEMO_FAULTS", raising=False)
    monkeypatch.setenv("SWAPDESK_DB", str(tmp_path / "reads.db"))
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


def _submit(client, case_id, **fields):
    body = {"message": f"ticket {case_id}", "case_id": case_id}
    body.update(fields)
    created = client.post("/v1/agent/tickets", json=body)
    assert created.status_code == 202, created.text
    return created.json()


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


def _counts():
    conn = connect(_db())
    try:
        return {
            t: conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"]
            for t in ("operations", "journal", "exchanges", "runs")}
    finally:
        conn.close()


def test_list_filters_pagination_summary_and_agreement(client):
    for cid in ("LIST-A", "LIST-B", "LIST-C"):
        _submit(client, cid, order_id="ORD-1001", order_item_id="ITEM-01",
                size="42")
    queued = client.get("/v1/agent/cases").json()
    assert queued["total"] == 3
    assert queued["summary"] == {"execution_status": {"queued": 3},
                                 "outcome": {"pending": 3},
                                 "completion": {"arranged": 0, "total": 3,
                                                "rate": "0%"}}
    assert queued["next_cursor"] is None  # single page
    _drain(_arrange_model)  # A arranges; B/C duplicate-reuse the exchange
    listed = client.get("/v1/agent/cases").json()
    assert listed["total"] == 3
    assert listed["summary"]["execution_status"] == {"completed": 3}
    assert listed["summary"]["outcome"] == {"arranged": 3}
    assert listed["summary"]["completion"] == {"arranged": 3, "total": 3,
                                               "rate": "100%"}
    assert len(listed["items"]) == 3
    # Detail agreement on every field the list exposes.
    for item in listed["items"]:
        detail = client.get(f"/v1/agent/cases/{item['case_id']}").json()
        for field in ("execution_status", "outcome", "current_run_id",
                      "runs", "reply"):
            assert item[field] == detail[field], (item["case_id"], field)
        assert item["message"].startswith("ticket ")
        assert item["order_id"] == "ORD-1001"
        assert item["size"] == "42"
        assert item["created_at"] <= item["updated_at"]
    # Filters.
    completed = client.get(
        "/v1/agent/cases?execution=completed").json()
    assert completed["total"] == 3
    assert all(i["execution_status"] == "completed"
               for i in completed["items"])
    assert client.get("/v1/agent/cases?execution=bogus").status_code == 422
    assert client.get("/v1/agent/cases?outcome=bogus").status_code == 422
    assert client.get("/v1/agent/cases?limit=0").status_code == 422
    assert client.get("/v1/agent/cases?limit=101").status_code == 422
    assert client.get("/v1/agent/cases?cursor=!!!").status_code == 422
    # Pagination walks the full population without overlap or gaps.
    seen, cursor = [], None
    while True:
        params = {"limit": 1}
        if cursor is not None:
            params["cursor"] = cursor
        page = client.get("/v1/agent/cases", params=params).json()
        assert page["total"] == 3
        assert page["summary"]["execution_status"] == {"completed": 3}
        seen.extend(i["case_id"] for i in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert sorted(seen) == ["LIST-A", "LIST-B", "LIST-C"]


def test_completion_rate_empty_and_partial(client):
    empty = client.get("/v1/agent/cases").json()
    assert empty["total"] == 0
    assert empty["summary"]["completion"] == {"arranged": 0, "total": 0,
                                              "rate": None}


def test_list_includes_escalation_without_business_state(client):
    _submit(client, "LIST-STALLED", order_id="ORD-1001",
            order_item_id="ITEM-01", size="42")
    stalled = ScriptedChatModel([AIMessage(content="nothing to do")])
    _drain(lambda: stalled)
    listed = client.get("/v1/agent/cases?execution=completed").json()
    match = [i for i in listed["items"] if i["case_id"] == "LIST-STALLED"]
    assert len(match) == 1
    assert match[0]["outcome"] == "escalation"
    assert "no progress" in (match[0]["reply"] or "")
    escalated = client.get("/v1/agent/cases?outcome=escalation").json()
    assert "LIST-STALLED" in [i["case_id"] for i in escalated["items"]]


def test_inventory_before_during_after_finalize(client):
    from swapdesk import operations as _ops

    db = _db()
    _queue.ensure_queue_schema(db)
    before = client.get(
        "/v1/inventory?sku=AIRFLOW-RUNNER&size=42").json()
    assert before["total"] == 1
    pool = before["items"][0]
    assert pool["available"] == pool["on_hand"] - pool["held"] == 10

    res = _ops.reserve_replacement(
        db, case_id="INV-1", run_id="RUN-1", op_key="INV-1:RUN-1:reserve",
        order_id="ORD-1001", order_item_id="ITEM-01", size="42")
    during = client.get(
        "/v1/inventory?sku=AIRFLOW-RUNNER&size=42").json()["items"][0]
    assert during["held"] == 1 and during["available"] == 9

    _ops.create_return(db, case_id="INV-1", run_id="RUN-1",
                       op_key="INV-1:RUN-1:return",
                       exchange_id=res.exchange_id)
    _ops.create_label(db, case_id="INV-1", run_id="RUN-1",
                      op_key="INV-1:RUN-1:label", exchange_id=res.exchange_id)
    _ops.finalize_arranged(db, case_id="INV-1", run_id="RUN-1",
                           op_key="INV-1:RUN-1:finalize",
                           exchange_id=res.exchange_id)
    after = client.get(
        "/v1/inventory?sku=AIRFLOW-RUNNER&size=42").json()["items"][0]
    # Finalize consumes the hold: stock down, hold released (unchanged
    # finalize behavior).
    assert after == {"sku": "AIRFLOW-RUNNER", "size": "42", "on_hand": 9,
                     "held": 0, "available": 9}
    assert set(after) == {"sku", "size", "on_hand", "held", "available"}

    paged = client.get("/v1/inventory?limit=5&offset=5").json()
    assert paged["limit"] == 5 and paged["offset"] == 5
    assert paged["total"] == 14 and len(paged["items"]) == 5
    assert [ (i["sku"], i["size"]) for i in paged["items"]] == sorted(
        (i["sku"], i["size"]) for i in paged["items"])
    assert client.get("/v1/inventory?limit=501").status_code == 422
    assert "read_at" in paged


def test_repeated_reads_cause_no_mutations_or_model_calls(client):
    _submit(client, "READ-ONLY", order_id="ORD-1001",
            order_item_id="ITEM-01", size="42")
    calls = []
    _drain(lambda: calls.append(1) or _arrange_model())
    assert len(calls) == 1
    before = _counts()
    for _ in range(2):
        client.get("/v1/agent/cases").json()
        client.get("/v1/agent/cases/READ-ONLY").json()
        client.get("/v1/agent/cases/READ-ONLY/timeline").json()
        client.get("/v1/inventory").json()
        client.get("/v1/ready").json()
    assert _counts() == before
    assert len(calls) == 1  # reads never invoke the model


def test_list_sanitizes_customer_text(client):
    secret = "sk-SECRETVALUE12345678"
    _submit(client, "SANITIZED",
            message=f"help api_key={secret} please")
    listed = client.get("/v1/agent/cases").json()
    match = [i for i in listed["items"] if i["case_id"] == "SANITIZED"]
    assert len(match) == 1
    assert secret not in match[0]["message"]
    assert secret not in json.dumps(listed)


def test_readiness_and_access_basics(client):
    ready = client.get("/v1/ready").json()
    assert ready["ok"] is True and ready["queued_depth"] == 0
    assert ready["oldest_queued_age_s"] is None
    assert "worker" in ready["note"].lower()
    _submit(client, "READY-Q")
    assert client.get("/v1/ready").json()["queued_depth"] == 1
    # Demo faults stay disabled; CORS headers are served for browsers.
    assert client.post("/v1/demo/faults", json={
        "case_id": "X", "run_id": "RUN-1",
        "step": "reserve", "point": "transient"}).status_code == 403
    cors = client.get("/v1/health",
                      headers={"Origin": "http://localhost:3000"})
    assert cors.headers.get("access-control-allow-origin") == \
        "http://localhost:3000"


def test_openapi_covers_new_reads(client):
    paths = client.get("/openapi.json").json()["paths"]
    for route in ("/v1/agent/cases", "/v1/inventory", "/v1/ready",
                  "/v1/agent/cases/{case_id}",
                  "/v1/agent/cases/{case_id}/timeline",
                  "/v1/agent/cases/{case_id}/continue"):
        assert route in paths, route


def _working_bash():
    import shutil
    import subprocess

    candidates = [
        r"C:\Program Files\Git\usr\bin\bash.exe",
        shutil.which("bash"),
    ]
    for candidate in candidates:
        if not candidate or "system32" in candidate.lower():
            continue  # WSL relay stub, not a shell
        try:
            probe = subprocess.run(
                [candidate, "--version"], capture_output=True, text=True,
                timeout=15)
            if probe.returncode == 0 and "gnu bash" in (
                    probe.stdout or "").lower():
                return candidate
        except Exception:
            continue
    return None


def test_entrypoint_supervision_with_fake_children():
    import subprocess

    bash = _working_bash()
    if bash is None:  # pragma: no cover - no usable bash here
        pytest.skip("no working bash; supervision semantics documented "
                    "in docker-entrypoint.sh")
    repo = Path(__file__).resolve().parent.parent
    env = dict(os.environ, SWAPDESK_WORKER_CMD="sleep 300",
               SWAPDESK_API_CMD="exit 3")
    # Inner `bash -c` calls must resolve to the same real bash, never the
    # System32 WSL relay stub that shares the name.
    bindir = str(Path(bash).resolve().parent)
    env["PATH"] = bindir + os.pathsep + env.get("PATH", "")
    proc = subprocess.run(
        [bash, str(repo / "docker-entrypoint.sh")], capture_output=True,
        text=True, timeout=60, env=env, cwd=str(repo))
    # First failing child (exit 3) terminates the run: status propagates,
    # and the run ends far sooner than the 300s sleeper (bounded cleanup).
    assert proc.returncode == 3, proc.stderr[-500:]
