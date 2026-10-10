# SwapDesk

SwapDesk arranges shoe exchanges for a fictional shop. A customer asks for a different size, and the backend checks policy and stock, holds a replacement, creates a return and a mock label, then verifies the saved state. Every request ends in one of four outcomes: exchange arranged, clarification required, policy denial, or human escalation. All data is synthetic. There are no payments, shipments, or real customers.

This repo holds the backend. It is a neatHack project, currently at Slice 5 of 7 (FastAPI for the frontend team). The demo does not exist yet.

## Features

Implemented:

- Atomic stock reservation with no oversell, safe under concurrent writers
- Idempotent operations: same key plus same payload returns the saved result, same key plus different payload is rejected
- Policy enforcement in the backend: delivered status, 30-day window, final sale excluded
- One active exchange per order item, across cases
- Append-only action journal for every committed or duplicate-routed operation
- Full mock exchange: return and label creation, hold release, cancel, escalation, case progress, read-only recovery handoff
- Controlled failure injection (demo-only `faults` module) with same-key recovery
- Deterministic pytest suite (34 tests, no network, no model)
- Independent checker plus frozen 30-case benchmark (`eval/cases_v1.json`, 8 holdouts, 42 runs)
- One LangGraph tool-using agent (`langchain.agents.create_agent`, Gemini): curated tools, bounded loop, file-backed checkpoints, DB-derived outcomes, template replies
- neatlogs wiring (workflow/tool spans, flush): local capture without a key, export with one

Planned, not built: FastAPI routes, business model in cfo.ai.

## Installation

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/adr1en360/SwapDesk.git
cd SwapDesk
uv sync
```

## Usage

Run the test suite:

```bash
uv run pytest -q
```

Reserve a replacement from a scratch database:

```bash
uv run python -c "
from swapdesk.db import connect, init_db
from swapdesk.fixtures import load_fixtures
from swapdesk.operations import reserve_replacement

conn = connect('scratch.db')
init_db(conn)
load_fixtures(conn)
conn.close()

result = reserve_replacement(
    'scratch.db', case_id='CASE-DEMO', run_id='RUN-DEMO', op_key='OP-DEMO',
    order_id='ORD-1001', order_item_id='ITEM-01', size='42')
print(result)
"
```

Check what a previous operation did:

```bash
uv run python -c "
from swapdesk.operations import get_operation_status
print(get_operation_status('scratch.db', 'OP-DEMO'))
"
```

Delete `scratch.db` when done. It is git-ignored.

## Studio verification

Full runbook with evidence: [docs/STUDIO_VERIFICATION.md](docs/STUDIO_VERIFICATION.md).

Two graphs share one architecture (`prepare` → nested `agent` subgraph → `verify`), defined in `src/swapdesk/agent/studio_flow.py` and served from `langgraph.json`:

```bash
uv run langgraph dev
```

Open Studio at `https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:8123` (override the port with `--port`). You will see two assistants:

- **`swapdesk_offline` (default).** A scripted model replays tool calls against the real backend. Zero model requests. This proves the wiring, never Gemini's decisions; the evidence panel labels every offline run accordingly.
- **`swapdesk_live` (opt-in).** Budget-capped Gemini. Each run needs an explicit request budget plus `SWAPDESK_MODEL` and `GEMINI_API_KEY`; anything missing fails loudly before any model call. Nothing live runs until you explicitly invoke a budgeted smoke test.

Example inputs (offline):

```json
{"scenario": "arrange"}
{"scenario": "deny", "case_id": "DEMO-DENY-2"}
{"scenario": "recover", "case_id": "DEMO-REC-2"}
{"case_id": "DEMO-ARRANGE-x1", "run_id": "RUN-x1", "resume": true, "message": "status check"}
```

Example input (live, budgeted):

```json
{"message": "Exchange ITEM-01 on order ORD-1001 for size 42.", "budget": 8}
```

What to inspect: expand the `agent` subgraph to see every model turn, tool call, and tool result as separate trace steps. Individual tools share one `tools` node because that is how the prebuilt agent compiles a tool list; nothing is hidden, each call still lands as its own `ToolMessage`. The `verify` node shows the outcome derived from persisted state, the database evidence (exchanges, operations, case state), and the rendered customer reply.

Rules the graphs enforce: one isolated database per case under `studio_data/` (git-ignored); reusing a case id without `"resume": true` errors instead of resetting; resume preserves the case, operation keys, and thread state. Thread persistence comes from the serving platform, so the served graphs compile without a custom checkpointer (the server rejects one); tests pass an explicit file saver to the same builders. The request cap counts every model request including retries and refuses past the budget; the recursion limit alone is not a request budget. Demo scenarios use fresh `DEMO-*` cases only and never load the frozen benchmark, so holdouts stay out of demo tuning. Opening Studio, importing the graphs, and running offline tests make zero model requests.

## API for frontend teammates

```bash
uv run uvicorn swapdesk.api:app
```

Interactive docs at `http://127.0.0.1:8000/docs` (generated from the implementation, always in sync). The demo database is `swapdesk.db` (override with `SWAPDESK_DB`); restarting reuses it, fixtures seed once.

| Method & route | What it does |
|---|---|
| `POST /v1/tickets` | Submit a ticket, run it to a verified outcome (201) |
| `GET /v1/cases/{id}` | Verified status, outcome, reply, run ids (404 unknown) |
| `GET /v1/cases/{id}/timeline` | Sanitized action/journal events (404 unknown) |
| `POST /v1/cases/{id}/continue` | Continue with message/consent (404 unknown, 422 uncontinuable) |
| `GET /v1/fixtures` | Synthetic orders, items, and policy for dropdowns |
| `POST /v1/demo/faults` | Demo-only: arm one failure on an operation key |
| `DELETE /v1/demo/faults` | Demo-only: disarm all failures |
| `GET /v1/health` | Liveness probe |

Outcomes (`arranged`, `clarification`, `denial`, `escalation`) always return 200 with an `outcome` field — a denial is an answer, not an error. Only malformed requests (422), unknown cases (404), and unexpected failures (500, generic message) are HTTP errors.

```bash
curl -X POST localhost:8000/v1/tickets \
  -H 'Content-Type: application/json' \
  -d '{"order_id":"ORD-1001","order_item_id":"ITEM-01","size":"42"}'

curl localhost:8000/v1/cases/CASE-xxx
curl localhost:8000/v1/cases/CASE-xxx/timeline
curl -X POST localhost:8000/v1/cases/CASE-xxx/continue \
  -H 'Content-Type: application/json' \
  -d '{"consent_size":"42","order_id":"ORD-1005","order_item_id":"ITEM-06","size":"43"}'

curl -X POST localhost:8000/v1/demo/faults \
  -H 'Content-Type: application/json' \
  -d '{"case_id":"DEMO-1","run_id":"RUN-1","step":"reserve","point":"transient","times":2}'
```

No authentication: this is a local mock. Execution runs synchronously per request, so status reads are never blocked.

## Configuration

- Return window and eligibility live in `src/swapdesk/policy.py` (`RETURN_WINDOW_DAYS = 30`).
- Each call takes a database path, so tests and scratch work never touch real files. There is no server config yet.
- Agent and telemetry read `.env` (git-ignored, never committed; see `.env.example` for the key names): `GEMINI_API_KEY`, `NEATLOGS_API_KEY`, `LITELLM_API_KEY` (all optional; without a model key the agent needs a passed-in model and telemetry stays local-only).
- The model provider swaps via env, never hardcoded: `LITELLM_API_KEY` set → hackathon LiteLLM proxy (OpenAI-compatible; `SWAPDESK_MODEL` picks from nova-micro/lite/pro, nova-2-lite, claude-haiku/sonnet-4.6/opus-4.6, default claude-haiku; override the endpoint with `LITELLM_BASE_URL`) — else `GEMINI_API_KEY` → direct Gemini (`SWAPDESK_MODEL`, default gemini-3.8-flash).
- Live model and telemetry export need working egress to Google APIs; where the network blocks them, the deterministic suites still pass.

## Project structure

```text
src/swapdesk/
  db.py          SQLite schema and transactions
  models.py      Typed records, states, transitions
  policy.py      Eligibility rules
  fixtures.py    Synthetic shop data
  operations.py  reserve/return/label/finalize/release/cancel/escalate/verify
  service.py     Deterministic ticket submit/continue/status for the API
  api.py         FastAPI routes, schemas, demo fault controls
  faults.py      Demo-only failure injection (tests, never production)
  checker.py     Deterministic benchmark checker (no LLM judge)
  telemetry.py   neatlogs init/wrap/flush (local-only without a key)
  agent/
    tools.py     Curated LangChain tools; identity injected per run
    context.py   Shared state, identity + budget middleware
    scripted.py  Offline scenario doubles (wiring only, never model proof)
    prompts.py   System prompt and verified reply templates
    graph.py     create_agent wiring, bounded runs, DB-derived outcomes
eval/
  cases_v1.json  Frozen 30-case benchmark (8 holdouts, seeded faults)
  driver.py      Deterministic reference driver (not the agent)
  harness.py     Isolated per-run execution and checking
  run.py         Regenerates eval/results/v1.json
tests/
  test_reservation.py
  test_exchange.py
  test_checker.py
  test_freeze.py
  test_agent.py
  test_studio.py
  test_api.py```

Build progress lives in [hackathon.md](hackathon.md). The full plan is in [docs/build-plan.md](docs/build-plan.md) (spec, not evidence).

## Development and testing

```bash
uv sync              # install dependencies
uv run pytest -q     # run the suite
uv add --dev <pkg>   # test-only dependency
uv add <pkg>         # runtime dependency
```

Business logic stays callable without HTTP or a model so tests never need a server or API key.

## Contributing

Backend owns `src/swapdesk/` and `tests/`. Frontend teammates consume the API contract (coming in Slice 5); no UI code lives here. Keep slices small, keep tests deterministic, and record each slice in `hackathon.md` with the exact commands run and pass/fail counts. Never commit `.env`, databases, or real customer data.

## License

No license chosen yet. Do not reuse this code until the owners add one.
