"""Slice 5 proofs: routes, schemas, outcomes, demo controls, OpenAPI."""

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from swapdesk import faults  # noqa: E402
from swapdesk import telemetry  # noqa: E402
from swapdesk.api import app  # noqa: E402


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch, tmp_path):
    monkeypatch.setenv("SWAPDESK_TELEMETRY_ENV", "0")
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
    monkeypatch.setenv("SWAPDESK_DB", str(tmp_path / "api.db"))
    faults.clear()
    yield
    faults.clear()


@pytest.fixture()
def client():
    return TestClient(app)


def test_health(client):
    assert client.get("/v1/health").json() == {
        "ok": True, "service": "swapdesk"}


def test_submit_arranged_and_read_back(client):
    created = client.post("/v1/tickets", json={
        "order_id": "ORD-1001", "order_item_id": "ITEM-01", "size": "42",
        "message": "need a 42"})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["outcome"] == "arranged"
    assert "TRK-MOCK-" in body["reply"]
    case_id = body["case_id"]

    status = client.get(f"/v1/cases/{case_id}").json()
    assert status["outcome"] == "arranged"
    assert status["exchange_id"] == body["exchange_id"]
    assert status["runs"] == ["RUN-1"]

    timeline = client.get(f"/v1/cases/{case_id}/timeline").json()
    assert [e["event"] for e in timeline] == [
        "reserved", "return_created", "label_created", "arranged"]
    assert all(e["status"] == "committed" for e in timeline)

    fixtures = client.get("/v1/fixtures").json()
    assert {o["id"] for o in fixtures["orders"]} == {
        "ORD-1001", "ORD-1002", "ORD-1003",
        "ORD-1004", "ORD-1005", "ORD-1006"}
    assert fixtures["policy"]["window_days"] == 30


def test_denial_and_clarification_are_200_outcomes(client):
    denied = client.post("/v1/tickets", json={
        "order_id": "ORD-1001", "order_item_id": "ITEM-02", "size": "40"})
    assert denied.status_code == 201
    assert denied.json()["outcome"] == "denial"
    assert denied.json()["exchange_id"] is None
    empty = client.get(
        f"/v1/cases/{denied.json()['case_id']}/timeline").json()
    assert empty == []

    vague = client.post("/v1/tickets", json={
        "order_id": "ORD-1001", "order_item_id": "ITEM-09", "size": "42"})
    assert vague.json()["outcome"] == "clarification"
    assert "order number" in vague.json()["reply"]


def test_continue_with_consent_arranges_alt_size(client):
    first = client.post("/v1/tickets", json={
        "order_id": "ORD-1005", "order_item_id": "ITEM-06", "size": "43"})
    assert first.json()["outcome"] == "clarification"
    case_id = first.json()["case_id"]

    second = client.post(f"/v1/cases/{case_id}/continue", json={
        "message": "42 is fine", "consent_size": "42",
        "order_id": "ORD-1005", "order_item_id": "ITEM-06", "size": "43"})
    body = second.json()
    assert body["outcome"] == "arranged"
    assert body["continued"] is True
    assert body["run_id"] == "RUN-1"

    from swapdesk.db import connect as _connect
    from swapdesk.operations import verify_exchange

    hand = verify_exchange(os.environ["SWAPDESK_DB"], body["exchange_id"])
    assert hand.consistent is True
    conn = _connect(os.environ["SWAPDESK_DB"])
    try:
        row = conn.execute("SELECT authorized_size, requested_size "
                           "FROM exchanges WHERE id = ?",
                           (body["exchange_id"],)).fetchone()
    finally:
        conn.close()
    assert row["requested_size"] == "43"
    assert row["authorized_size"] == "42"


def test_continue_terminal_reports_unchanged(client):
    first = client.post("/v1/tickets", json={
        "order_id": "ORD-1002", "order_item_id": "ITEM-03", "size": "42"})
    assert first.json()["outcome"] == "arranged"
    again = client.post(
        f"/v1/cases/{first.json()['case_id']}/continue", json={})
    body = again.json()
    assert body["continued"] is False
    assert body["outcome"] == "arranged"
    assert body["exchange_id"] == first.json()["exchange_id"]


def test_cross_case_duplicate_reuses_exchange(client):
    one = client.post("/v1/tickets", json={
        "order_id": "ORD-1003", "order_item_id": "ITEM-04", "size": "44"})
    two = client.post("/v1/tickets", json={
        "order_id": "ORD-1003", "order_item_id": "ITEM-04", "size": "44"})
    assert one.json()["outcome"] == "arranged"
    assert two.json()["outcome"] == "arranged"
    assert two.json()["exchange_id"] == one.json()["exchange_id"]


def test_unknown_case_and_validation(client):
    assert client.get("/v1/cases/CASE-NOPE").status_code == 404
    assert client.get("/v1/cases/CASE-NOPE/timeline").status_code == 404
    assert client.post("/v1/cases/CASE-NOPE/continue",
                       json={}).status_code == 404
    bad = client.post("/v1/tickets", json={
        "order_id": "ORD-1001", "order_item_id": "ITEM-01", "size": "42",
        "qty": 0})
    assert bad.status_code == 422
    stuck = client.post("/v1/tickets", json={
        "order_id": "ORD-1005", "order_item_id": "ITEM-06", "size": "43"})
    no_request = client.post(
        f"/v1/cases/{stuck.json()['case_id']}/continue", json={})
    assert no_request.status_code == 422


def test_demo_fault_recovery_and_controls(client):
    armed = client.post("/v1/demo/faults", json={
        "case_id": "DEMO-API", "run_id": "RUN-1",
        "step": "reserve", "point": "transient", "times": 2})
    assert armed.json()["armed"] is True
    assert armed.json()["op_key"] == "DEMO-API:RUN-1:reserve"

    created = client.post("/v1/tickets", json={
        "order_id": "ORD-1001", "order_item_id": "ITEM-01", "size": "42",
        "case_id": "DEMO-API"})
    body = created.json()
    assert body["outcome"] == "arranged"
    assert body["attempts"]["reserve"] == 3

    cleared = client.delete("/v1/demo/faults").json()
    assert cleared == {"cleared": True}

    assert client.post("/v1/demo/faults", json={
        "case_id": "X", "step": "nope", "point": "transient"}
    ).status_code == 422
    assert client.post("/v1/demo/faults", json={
        "case_id": "X", "step": "reserve", "point": "nope"}
    ).status_code == 422


def test_openapi_matches_implementation(client):
    doc = client.get("/openapi.json").json()
    paths = doc["paths"]
    for route in ("/v1/health", "/v1/tickets", "/v1/cases/{case_id}",
                  "/v1/cases/{case_id}/timeline",
                  "/v1/cases/{case_id}/continue", "/v1/fixtures",
                  "/v1/demo/faults"):
        assert route in paths, route
    ticket_fields = paths["/v1/tickets"]["post"]["requestBody"][
        "content"]["application/json"]["schema"]
    assert ticket_fields["$ref"].endswith("TicketIn")
    props = doc["components"]["schemas"]["TicketIn"]["properties"]
    assert {"order_id", "order_item_id", "size"} <= set(props)


def test_telemetry_helpers_do_not_leak():
    assert telemetry.init_telemetry(
        workflow_name="swapdesk-api-test") is False
