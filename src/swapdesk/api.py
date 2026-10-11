"""HTTP API for frontend teammates. One concern only: HTTP ↔ service.

Two customer-adjacent paths:
- Agent path (`/v1/agent/*`): the customer frontend contract. POST saves
  the request and returns 202 accepted with a status location; a worker
  executes service.submit_agent_ticket per claimed run. Execution status
  (queued/running/waiting_input/completed/failed) is distinct from the
  business outcome (arranged/clarification/denial/escalation, null until
  a run completes). Status/timeline reads are read-only and never block.
- Legacy deterministic path (`/v1/tickets`, `/v1/cases/*`): synchronous
  demo policy without a model. Documented for benchmarks only; the
  customer frontend must not use it.

HTTP errors mean transport problems only: 404 unknown case, 422 bad
request, 409 submission conflict or concurrent run, 403 disabled demo
controls, 503 unconfigured agent, 502 failed agent run, 500 unexpected
failure (generic message, never internals). No authentication: this is
a local mock, and the docs say so. Demo-only failure controls live
under /v1/demo, are disabled by default, and never touch customer
execution.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import queue, service
from .operations import OperationError
from .queue import ConcurrentRun, SubmissionConflict

FAULT_POINTS = {"transient", "deplete_stock", "crash", "timeout",
                "release_fail"}
FAULT_STEPS = {"reserve", "return", "label", "finalize", "escalate",
               "cancel"}


class TicketIn(BaseModel):
    order_id: str
    order_item_id: str
    size: str = ""
    qty: int = Field(default=1, ge=1)
    message: str = ""
    consent_size: str | None = None
    case_id: str | None = None


class TicketOut(BaseModel):
    case_id: str
    run_id: str
    outcome: str
    reply: str
    exchange_id: str | None = None
    attempts: dict = {}


class AgentTicketIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    order_id: str | None = Field(default=None, max_length=96)
    order_item_id: str | None = Field(default=None, max_length=96)
    size: str | None = Field(default=None, max_length=32)
    qty: int = Field(default=1, ge=1)
    consent_size: str | None = Field(default=None, max_length=32)
    case_id: str | None = Field(default=None, min_length=1, max_length=96)
    idempotency_key: str | None = Field(default=None, min_length=1,
                                        max_length=96)
    resume: bool = False


class AgentTicketOut(BaseModel):
    case_id: str
    run_id: str
    outcome: str
    reply: str
    exchange_id: str | None = None
    resumed: bool


class AgentAccepted(BaseModel):
    case_id: str
    run_id: str
    execution_status: str
    status_url: str
    duplicate: bool = False


class AgentStatusOut(BaseModel):
    case_id: str
    execution_status: str
    outcome: str | None = None
    reply: str | None = None
    exchange_id: str | None = None
    runs: list[str] = []
    current_run_id: str | None = None
    clarification: str | None = None
    cleanup: str | None = None
    trace_id: str | None = None
    error: str | None = None
    requests_spent: int | None = None


class AgentContinueIn(BaseModel):
    message: str = Field(default="", max_length=4000)
    consent_size: str | None = Field(default=None, max_length=32)
    order_id: str | None = Field(default=None, max_length=96)
    order_item_id: str | None = Field(default=None, max_length=96)
    size: str | None = Field(default=None, max_length=32)
    qty: int = Field(default=1, ge=1)


class AgentContinueOut(BaseModel):
    case_id: str
    run_id: str | None = None
    execution_status: str
    continued: bool
    outcome: str | None = None
    reply: str | None = None
    exchange_id: str | None = None


class ContinueIn(BaseModel):
    message: str = ""
    consent_size: str | None = None
    order_id: str | None = None
    order_item_id: str | None = None
    size: str | None = None
    qty: int = Field(default=1, ge=1)


class ContinueOut(BaseModel):
    case_id: str
    run_id: str | None = None
    outcome: str
    reply: str
    exchange_id: str | None = None
    attempts: dict = {}
    continued: bool


class StatusOut(BaseModel):
    case_id: str
    outcome: str
    reply: str
    exchange_id: str | None = None
    runs: list[str] = []


class TimelineEvent(BaseModel):
    op_key: str
    run_id: str | None = None
    op_type: str | None = None
    event: str
    status: str | None = None
    result: Any = None
    created_at: str


class FixtureItem(BaseModel):
    id: str
    sku: str
    size: str
    qty: int
    status: str
    delivered_at: str | None = None
    final_sale: bool


class FixtureOrder(BaseModel):
    id: str
    customer_ref: str
    items: list[FixtureItem]


class FixturesOut(BaseModel):
    orders: list[FixtureOrder]
    policy: dict


class FaultIn(BaseModel):
    case_id: str
    run_id: str = "RUN-1"
    step: str
    point: str
    times: int = Field(default=1, ge=1)


class FaultOut(BaseModel):
    armed: bool
    op_key: str
    point: str
    times: int


def _cors_origins() -> list[str]:
    raw = os.environ.get(
        "SWAPDESK_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000")
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(title="SwapDesk",
              version="0.2.0",
              description="Local mock exchange backend. No auth, no real "
                          "payments, shipments, or customers. Agent tickets "
                          "are accepted asynchronously (202); legacy ticket "
                          "routes run the deterministic demo policy.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _db() -> Path:
    return service.default_db_path()


def _demo_enabled() -> bool:
    return os.environ.get("SWAPDESK_ENABLE_DEMO_FAULTS") == "1"


@app.get("/v1/health", tags=["meta"])
def health() -> dict:
    return {"ok": True, "service": "swapdesk"}


@app.post("/v1/tickets", response_model=TicketOut, status_code=201,
          tags=["tickets"])
def submit_ticket(body: TicketIn) -> dict:
    try:
        return service.submit_ticket(
            _db(), order_id=body.order_id,
            order_item_id=body.order_item_id, size=body.size, qty=body.qty,
            message=body.message, consent_size=body.consent_size,
            case_id=body.case_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except OperationError:
        return JSONResponse(
            status_code=500, content={"detail": "internal error"})


@app.post("/v1/agent/tickets", response_model=AgentAccepted,
          status_code=202, tags=["tickets"])
def submit_agent_ticket(body: AgentTicketIn) -> dict:
    """Accept an agent ticket for worker execution. 202 accepted, never
    completion: poll the status_url for execution status and outcome."""
    if body.resume and not body.case_id:
        raise HTTPException(
            status_code=422, detail="resume requires case_id")
    try:
        accepted = queue.submit_agent_request(
            _db(), message=body.message, order_id=body.order_id,
            order_item_id=body.order_item_id, size=body.size, qty=body.qty,
            consent_size=body.consent_size, case_id=body.case_id,
            idempotency_key=body.idempotency_key)
    except SubmissionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {**accepted,
            "status_url": f"/v1/agent/cases/{accepted['case_id']}"}


@app.get("/v1/agent/cases/{case_id}", response_model=AgentStatusOut,
         tags=["cases"])
def read_agent_case(case_id: str) -> dict:
    status = queue.get_agent_status(_db(), case_id)
    if status is None:
        raise HTTPException(status_code=404, detail="unknown case")
    return status


@app.get("/v1/agent/cases/{case_id}/timeline",
         response_model=list[TimelineEvent], tags=["cases"])
def read_agent_timeline(case_id: str) -> list:
    timeline = queue.get_agent_timeline(_db(), case_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail="unknown case")
    return timeline


@app.post("/v1/agent/cases/{case_id}/continue",
          response_model=AgentContinueOut, tags=["cases"])
def continue_agent_case(case_id: str, body: AgentContinueIn):
    """Continue through the same agent path. Terminal cases return their
    saved result with continued=false and no model call."""
    if queue.get_agent_status(_db(), case_id) is None:
        raise HTTPException(status_code=404, detail="unknown case")
    try:
        out = queue.continue_agent_request(
            _db(), case_id=case_id, message=body.message,
            consent_size=body.consent_size, order_id=body.order_id,
            order_item_id=body.order_item_id, size=body.size, qty=body.qty)
    except ConcurrentRun as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if out is None:
        raise HTTPException(status_code=404, detail="unknown case")
    if out.get("continued"):
        return JSONResponse(status_code=202, content=out)
    return out


@app.get("/v1/cases/{case_id}", response_model=StatusOut, tags=["cases"])
def read_case(case_id: str) -> dict:
    status = service.case_status(_db(), case_id)
    if status is None:
        raise HTTPException(status_code=404, detail="unknown case")
    return status


@app.get("/v1/cases/{case_id}/timeline",
         response_model=list[TimelineEvent], tags=["cases"])
def read_timeline(case_id: str) -> list:
    timeline = service.case_timeline(_db(), case_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail="unknown case")
    return timeline


@app.post("/v1/cases/{case_id}/continue", response_model=ContinueOut,
          tags=["cases"])
def continue_case(case_id: str, body: ContinueIn) -> dict:
    if service.case_status(_db(), case_id) is None:
        raise HTTPException(status_code=404, detail="unknown case")
    try:
        return service.continue_case(
            _db(), case_id=case_id, message=body.message,
            consent_size=body.consent_size, order_id=body.order_id,
            order_item_id=body.order_item_id, size=body.size, qty=body.qty)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except OperationError:
        return JSONResponse(
            status_code=500, content={"detail": "internal error"})


@app.get("/v1/fixtures", response_model=FixturesOut, tags=["fixtures"])
def read_fixtures() -> dict:
    return service.fixture_catalog(_db())


@app.post("/v1/demo/faults", response_model=FaultOut, tags=["demo"])
def arm_fault(body: FaultIn) -> dict:
    if not _demo_enabled():
        raise HTTPException(
            status_code=403,
            detail="demo faults disabled; set SWAPDESK_ENABLE_DEMO_FAULTS=1 "
                   "for explicit local testing")
    if body.step not in FAULT_STEPS:
        raise HTTPException(
            status_code=422,
            detail=f"unknown step; choose one of {sorted(FAULT_STEPS)}")
    if body.point not in FAULT_POINTS:
        raise HTTPException(
            status_code=422,
            detail=f"unknown point; choose one of {sorted(FAULT_POINTS)}")
    return service.arm_demo_fault(case_id=body.case_id, run_id=body.run_id,
                                  step=body.step, point=body.point,
                                  times=body.times)


@app.delete("/v1/demo/faults", tags=["demo"])
def clear_faults() -> dict:
    if not _demo_enabled():
        raise HTTPException(
            status_code=403,
            detail="demo faults disabled; set SWAPDESK_ENABLE_DEMO_FAULTS=1 "
                   "for explicit local testing")
    return service.clear_demo_faults()
