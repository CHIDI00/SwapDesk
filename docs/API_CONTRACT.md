# SwapDesk customer frontend contract (agent path)

Status: normative for the `/v1/agent/*` routes in `src/swapdesk/api.py`.
OpenAPI at `/openapi.json` is generated from the implementation.
For Joshua and Chidi: integrate against this document, not the legacy
routes below.

> Change notice: `POST /v1/agent/tickets` used to run the agent inline
> and return `201` with the completed outcome. It now persists the
> request and returns **`202 accepted`** with `case_id`, `run_id`,
> `execution_status`, and `status_url`. Poll the status URL: nothing in
> the accept response claims completion.

## Startup

```bash
uv run uvicorn swapdesk.api:app --port 8000
uv run python -m swapdesk.worker
```

API and worker share `SWAPDESK_DB` (default `swapdesk.db`). Agent
checkpoints live at `<db>.agent-checkpoints.sqlite`. knobs:

| Variable | Default | Purpose |
|---|---|---|
| `SWAPDESK_WORKER_POLL_MS` | `200` | Queue poll interval |
| `SWAPDESK_AGENT_BUDGET` | `12` | Max provider requests per run (hard cap, not a recursion limit) |
| `SWAPDESK_RUN_TIMEOUT_S` | `300` | Wall-clock execution timeout per run |
| `SWAPDESK_ENABLE_DEMO_FAULTS` | unset (disabled) | Set `1` for explicit local fault testing |
| `SWAPDESK_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Allowed frontend origins |

## Concepts

- `execution_status`: queue/worker state — `queued | running |
  waiting_input | completed | failed`.
- `outcome`: business result — `arranged | clarification | denial |
  escalation | null` (`null` until a run completes).
- `clarification` parks the case in `waiting_input`; continue through the
  same agent path with message/consent.
- Terminal outcomes (`arranged`, `denial`, `escalation`) return their
  saved result with no further model call.
- `trace_id` is the local checkpoint thread (`case_id:run_id`); `null`
  when no run completed. Never a URL, never invented.
- Timeline holds journal/operation events only (ids, sizes, policy
  phrases). Agent reasoning and credentials are never exposed.
- Failed or timed-out runs are never retried automatically; an explicit
  continue queues a fresh run. Cancellation limits: an in-flight model
  call cannot be cancelled, so a timed-out attempt may still commit late;
  operation keys are idempotent, so late commits cannot double-apply.

## POST /v1/agent/tickets → 202

Request:

```json
{
  "message": "My Jordan 4s are too tight, need size 43",
  "order_id": "ORD-1001",
  "order_item_id": "ITEM-01",
  "size": "43",
  "qty": 1,
  "consent_size": null,
  "case_id": null,
  "idempotency_key": "storefront-abc-123"
}
```

- `message` is required and non-blank. `order_id` / `order_item_id` /
  `size` may be missing: the agent asks for information instead.
- Supplied fields travel as structured request data; `consent_size` is
  recorded only when explicitly supplied, never fabricated.
- Idempotency: effective key = `idempotency_key` or `case_id`. Same key
  + same payload returns the existing case (`duplicate: true`, no new
  run). Same key + different payload is `409`.

Response `202`:

```json
{
  "case_id": "CASE-9f3a2c1b",
  "run_id": "RUN-1",
  "execution_status": "queued",
  "status_url": "/v1/agent/cases/CASE-9f3a2c1b",
  "duplicate": false
}
```

Errors: `422` validation, `409` key conflict.

## GET /v1/agent/cases/{case_id} → 200

```json
{
  "case_id": "CASE-9f3a2c1b",
  "execution_status": "completed",
  "outcome": "arranged",
  "reply": "Exchange arranged: return RET-EXC-ITEM-01-1 created, label LBL-EXC-ITEM-01-1 (TRK-MOCK-EXC-ITEM-01-1) ready. Reservation EXC-ITEM-01-1 verified.",
  "exchange_id": "EXC-ITEM-01-1",
  "runs": ["RUN-1"],
  "current_run_id": "RUN-1",
  "clarification": null,
  "cleanup": "none",
  "trace_id": "CASE-9f3a2c1b:RUN-1",
  "error": null,
  "requests_spent": 7
}
```

While `queued`/`running`, `outcome`, `reply`, and `exchange_id` are
`null`. `clarification` carries the question when `outcome` is
`clarification`. `error` carries a sanitized reason only when `failed`.
`requests_spent` is the client-counted model generations consumed by the
latest run (usage ground truth; token figures come from traces when
captured). `404` unknown case. Read-only; never blocks on the worker.

## GET /v1/agent/cases/{case_id}/timeline → 200

```json
[
  {
    "op_key": "CASE-9f3a2c1b:RUN-1:reserve",
    "run_id": "RUN-1",
    "op_type": "reserve_replacement",
    "event": "reserved",
    "status": "committed",
    "result": {"exchange_id": "EXC-ITEM-01-1", "status": "replacement_reserved"},
    "created_at": "2026-10-11T07:00:00+00:00"
  }
]
```

Empty list before anything commits. `404` unknown case.

## POST /v1/agent/cases/{case_id}/continue → 202 or 200

Request (at least one input required):

```json
{
  "message": "42 is fine",
  "consent_size": "42",
  "order_id": null,
  "order_item_id": null,
  "size": null,
  "qty": 1
}
```

- Waiting/failed case → `202` with `continued: true` and the new `run_id`
  (`RUN-2`, …). Recorded consent is preserved; explicit `consent_size`
  overrides. Prior action keys are untouched (fresh run, fresh keys).
- Terminal case → `200` with `continued: false` and the saved
  outcome/reply. No model call, no new exchange.
- Queued/running case → `409` (finish or fail first; one run per case).
- `404` unknown case, `422` empty continuation.

New-work response `202`:

```json
{
  "case_id": "CASE-9f3a2c1b",
  "run_id": "RUN-2",
  "execution_status": "queued",
  "continued": true,
  "outcome": null,
  "reply": null,
  "exchange_id": null
}
```

Terminal response `200`:

```json
{
  "case_id": "CASE-9f3a2c1b",
  "run_id": "RUN-1",
  "execution_status": "completed",
  "continued": false,
  "outcome": "arranged",
  "reply": "Exchange arranged: ...",
  "exchange_id": "EXC-ITEM-01-1"
}
```

## Legacy routes (benchmarks only — frontend must not use)

- `POST /v1/tickets` (201, synchronous deterministic policy),
  `GET /v1/cases/{id}`, `GET /v1/cases/{id}/timeline`,
  `POST /v1/cases/{id}/continue`. Unchanged behavior.
- `POST /v1/demo/faults`, `DELETE /v1/demo/faults`: `403` unless
  `SWAPDESK_ENABLE_DEMO_FAULTS=1`. Customer execution never depends on
  them.
- `GET /v1/fixtures`, `GET /v1/health`: unchanged, safe for the frontend.
