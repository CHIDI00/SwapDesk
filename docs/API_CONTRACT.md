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
  "message": "Please exchange ITEM-01 on order ORD-1001 for size 42",
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

## GET /v1/agent/cases → 200 (inbox list)

Newest first. Read-only: no model calls, no business writes. Each item
uses the same resolver as the detail endpoint (list/detail agree),
including runs without business state. `total` and `summary` cover the
full filtered population, not the page.

Query params: `execution` (one of `queued|running|waiting_input|
completed|failed`), `outcome` (one of `arranged|clarification|denial|
escalation`), `limit` (default 25, max 100), `cursor` (opaque,
from a previous `next_cursor`). Invalid values are `422`.

```json
{
  "items": [
    {
      "case_id": "CASE-9f3a2c1b",
      "message": "Please exchange ITEM-01 on order ORD-1001 for size 42",
      "order_id": "ORD-1001",
      "order_item_id": "ITEM-01",
      "size": "42",
      "qty": 1,
      "execution_status": "completed",
      "outcome": "arranged",
      "current_run_id": "RUN-1",
      "runs": ["RUN-1"],
      "created_at": "2026-10-11T07:00:00+00:00",
      "updated_at": "2026-10-11T07:00:18+00:00",
      "reply": "Exchange arranged: ..."
    }
  ],
  "next_cursor": null,
  "total": 1,
  "summary": {
    "execution_status": {"completed": 1},
    "outcome": {"arranged": 1}
  }
}
```

`outcome: null` reads as `"pending"` in the outcome summary. The
`summary` also carries `completion` (`arranged`, `total`, `rate` as a
whole-percent string, `null` when `total` is 0) computed from the same
resolver, so the displayed rate always agrees with list and detail. The
customer `message` is credential-scrubbed before return.

## GET /v1/inventory → 200 (real stock)

Actual stock keyed by SKU and size, ordered by `(sku, size)`.
`available = on_hand - held`. Only SKU/size/count fields — no
warehouse or product names invented. Pure read: unknown database reads
as empty; nothing is seeded, reserved, released, or reset.

Query params: `sku` / `size` (exact match), `limit` (default 100, max
500), `offset` (default 0).

```json
{
  "items": [
    {"sku": "AIRFLOW-RUNNER", "size": "42",
     "on_hand": 9, "held": 0, "available": 9}
  ],
  "limit": 100,
  "offset": 0,
  "total": 14,
  "read_at": "2026-10-11T07:05:00+00:00"
}
```

## GET /v1/ready → 200 (deployment signal, not proof)

Queue-state readiness for the single-worker SQLite deployment:
`queued_depth`, `oldest_queued_age_s`, `last_terminal_at`. A healthy
`/v1/health` with growing queued depth/age means no worker is draining.
This endpoint cannot prove a worker process is alive.

```json
{
  "ok": true,
  "service": "swapdesk",
  "queued_depth": 0,
  "oldest_queued_age_s": null,
  "last_terminal_at": "2026-10-11T07:00:18+00:00",
  "note": "queue state only: a growing queued depth or age means no worker is draining, not that one is healthy"
}
```

## Access posture before public paid intake (analysis, no change made)

- CORS is not authentication: it only lets browsers call. Anyone with
  the URL can submit paid agent tickets today.
- Per-run request caps bound generations per run, not aggregate spend:
  there is no rate limiting and no cross-case budget.
- Secrets today: provider/telemetry keys live only as server env vars
  (never in the browser bundle, never in the image: `.env*`, `*.pem`,
  `*.key` excluded from the build context). Keep it that way.
- Demo faults stay disabled unless explicitly enabled.
- Recommended before any public paid intake (not implemented here):
  a verified platform access gate (private service + identity-aware
  proxy) or minimal server-side protection (admin key on `POST`
  routes plus per-IP rate limits). No access was changed in this task,
  and nothing here was deployed.
