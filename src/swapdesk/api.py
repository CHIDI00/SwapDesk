"""HTTP API for frontend teammates. One concern only: HTTP ↔ service.

Business outcomes (arranged/clarification/denial/escalation) are always
HTTP 200 with an `outcome` field: a denial is an answer, not an error.
HTTP errors mean transport problems only: 404 unknown case, 422 bad
request, 500 unexpected failure (generic message, never internals).

Execution is synchronous per request; the demo database makes status
reads available at any time. No authentication: this is a local mock,
and the docs say so. Demo-only failure controls live under /v1/demo
and never touch ordinary endpoints.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import service
from .agent.graph import ConfigurationError
from .operations import OperationError

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
    resume: bool = False


class AgentTicketOut(BaseModel):
    case_id: str
    run_id: str
    outcome: str
    reply: str
    exchange_id: str | None = None
    resumed: bool


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


app = FastAPI(title="SwapDesk",
              version="0.1.0",
              description="Local mock exchange backend. No auth, no real "
                          "payments, shipments, or customers.")


def _db() -> Path:
    return service.default_db_path()


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


@app.post("/v1/agent/tickets", response_model=AgentTicketOut,
          status_code=201, tags=["tickets"])
def submit_agent_ticket(body: AgentTicketIn) -> dict:
    try:
        return service.submit_agent_ticket(
            _db(), message=body.message, order_id=body.order_id,
            order_item_id=body.order_item_id, size=body.size, qty=body.qty,
            consent_size=body.consent_size, case_id=body.case_id,
            resume=body.resume)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ConfigurationError:
        raise HTTPException(status_code=503,
                            detail="agent is not configured")
    except service.AgentExecutionError as exc:
        return JSONResponse(status_code=502, content={
            "detail": "agent execution failed; retry with the same case_id "
                      "and resume=true",
            "case_id": exc.case_id, "run_id": exc.run_id,
        })
    except OperationError:
        return JSONResponse(
            status_code=500, content={"detail": "internal error"})


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
    return service.clear_demo_faults()
