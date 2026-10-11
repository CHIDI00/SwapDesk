# SwapDesk

SwapDesk arranges shoe exchanges for a fictional shop. A customer asks for a different size, and the system checks policy and stock, holds a replacement, creates a return and a mock label, then verifies the saved state. Every request ends in one of four outcomes: **exchange arranged**, **clarification required**, **policy denial**, or **human escalation**.

All data is synthetic. There are no payments, shipments, or real customers. This is a neatHack project built by a team of four.

## Repository layout

```text
frontend/          Next.js dashboard — standalone client-side demo (no backend required)
src/swapdesk/      Python backend package — FastAPI, SQLite, LangGraph agent
eval/              Frozen benchmark, deterministic checker, and run harness
tests/             Deterministic pytest suite (no network, no model)
docs/              Build plan, runbooks, evidence, and business deliverables
hackathon.md       Slice-by-slice build log and team conventions
```

## The two halves

- **Backend** (`src/swapdesk/`) — the agent runtime. Policy checks, atomic stock reservation, idempotent operations, an append-only action journal, a LangGraph tool-using agent, and a FastAPI surface for frontend integration. Deterministic and network-free to test.
- **Frontend** (`frontend/`) — the ops dashboard (Mission Control, Inbox, Inventory, Integrations, Customer Simulation, ticket detail). It is a **self-contained client-side demo** powered by a mock store — it demos the SwapDesk experience without calling the live API. Its own README lives at [`frontend/README.md`](frontend/README.md).

---

## Backend

### Features

- Atomic stock reservation with no oversell, safe under concurrent writers.
- Idempotent operations: same key plus same payload returns the saved result; same key plus different payload is rejected.
- Policy enforcement: delivered status, 30-day return window, final-sale excluded.
- One active exchange per order item, across cases.
- Append-only action journal for every committed or duplicate-routed operation.
- Full mock exchange lifecycle: reserve → return → label → arrange, plus hold release, cancel, escalation, cleanup recovery, and a read-only verification handoff.
- Demo-only failure injection (`faults.py`) with same-key recovery.
- A LangGraph tool-using agent (`langchain.agents.create_agent`, Gemini or a LiteLLM proxy): curated tools, bounded loop, budget-capped requests, file-backed checkpoints, database-derived outcomes, template replies.
- neatlogs wiring (workflow/tool spans, local capture without a key, export with one).

### Installation

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/adr1en360/SwapDesk.git
cd SwapDesk
uv sync
```

### Test

```bash
uv run pytest -q
```

The suite is deterministic — no network, no model keys, no LLM judge.

### Run the API

```bash
uv run uvicorn swapdesk.api:app
```

Interactive docs at `http://127.0.0.1:8000/docs` (generated from the implementation, always in sync). The demo database is `swapdesk.db` (override with `SWAPDESK_DB`); restarting reuses it, fixtures seed once.

| Method & route | What it does |
|---|---|
| `POST /v1/tickets` | Submit a ticket and run it to a verified outcome (201) |
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
```

No authentication: this is a local mock. Execution runs synchronously per request, so status reads are never blocked.

### Configuring the agent

Copy `.env.example` to `.env` and fill in what you have (`.env` is git-ignored; never commit it):

- `GEMINI_API_KEY` — direct Gemini access (no `LITELLM_API_KEY`).
- `LITELLM_API_KEY` — enables the hackathon LiteLLM proxy instead; `SWAPDESK_MODEL` then picks from `nova-micro`, `nova-lite`, `nova-pro`, `nova-2-lite`, `claude-haiku`, `claude-sonnet-4.6`, `claude-opus-4.6` (default `claude-haiku`). Override the endpoint with `LITELLM_BASE_URL`.
- `SWAPDESK_MODEL` — Gemini model id when using Gemini directly (default `gemini-3.8-flash`).
- `NEATLOGS_API_KEY` + `NEATLOGS_PROJECT_ID` — neatlogs telemetry export; local-only capture works without them.

Live model calls and telemetry export need working egress to the upstream APIs; where the network blocks them, the deterministic suites still pass.

### Inspecting the agent in LangGraph Studio

Two graphs share one architecture (`prepare` → nested `agent` subgraph → `verify`), defined in `src/swapdesk/agent/studio_flow.py` and served from `langgraph.json`:

```bash
uv run langgraph dev
```

Open Studio at `https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:8123`. Two assistants are registered:

- **`swapdesk_offline` (default).** A scripted model replays tool calls against the real backend — zero model requests. Proves the wiring, never Gemini's decisions.
- **`swapdesk_live` (opt-in).** Budget-capped Gemini. Needs `SWAPDESK_MODEL` plus `GEMINI_API_KEY` (or the LiteLLM pair) and a per-run budget; anything missing fails loudly before any model call.

Full runbook with evidence: [`docs/STUDIO_VERIFICATION.md`](docs/STUDIO_VERIFICATION.md).

## Frontend

A Next.js 16 (Turbopack) App Router dashboard with React 19, TypeScript, and Tailwind CSS v4.

### Run it

```bash
cd frontend
npm install
npm run dev      # http://localhost:3000
```

Other scripts: `npm run build` (production build), `npm run start`, `npm run lint`.

### Pages and demo flow

| Route | Page | What it demos |
|---|---|---|
| `/` | Mission Control | Agent metrics + live execution queue |
| `/inbox` | Inbox | Sample ticket stream |
| `/inventory` | Inventory | Stock levels that react to simulations |
| `/database` | Database Schema | Tables the agent reads/writes |
| `/integrations` | Integrations | Inbound webhook triggers (Zendesk, Shopify, Gorgias) |
| `/settings` | Agent Settings | Autonomy/guardrail config UI |
| `/simulate` | Customer Simulation | Inject a customer complaint into the queue |
| `/ticket/[id]` | Ticket Execution | Per-ticket action timeline |

The demo runs entirely on a client-side store (`frontend/src/store/swapdesk.tsx`). **Simulate Ticket** prepends a resolved ticket and decrements `AJ4-MIL-43` stock; **Customer Simulation** injects a ticket with an `Agent Processing` status; **Reset Mock Data** (inventory page) restores the initial state. Dashboard labels reflect the actual mock state — completion rate is computed from the queue, and cost shows "Demo Mode".

SEO is configured across all routes (per-page metadata, generated Open Graph/Twitter images, `robots.txt`, `sitemap.xml`). See [`frontend/README.md`](frontend/README.md) and [`frontend/setup.md`](frontend/setup.md) for details.

## Evaluation and evidence

- `eval/cases_v1.json` — frozen 30-case benchmark (`benchmark-v1`, 8 holdouts) covering arrangement, denial, clarification, and escalation, with seeded fault schedules.
- `eval/driver.py` — deterministic reference driver (not the agent) that exercises the cases.
- `eval/harness.py` + `eval/run.py` — isolated database per run; results committed to `eval/results/v1.json`.
- `src/swapdesk/checker.py` — deterministic per-outcome checks and global invariants, no LLM judge.
- `docs/EVIDENCE_RUNNER_HARNESS.md` — a controlled live BEFORE/AFTER comparison of the D1 final-sale denial evidence path.

## Documentation

| Doc | Purpose |
|---|---|
| [`docs/build-plan.md`](docs/build-plan.md) | Full build plan (spec, not evidence) |
| [`docs/STUDIO_VERIFICATION.md`](docs/STUDIO_VERIFICATION.md) | LangGraph Studio runbook with evidence |
| [`docs/EVIDENCE_RUNNER_HARNESS.md`](docs/EVIDENCE_RUNNER_HARNESS.md) | Runner/harness evidence walk-through |
| [`docs/business/`](docs/business/) | Business plan (MD/PDF) and financial model (XLSX) — figures are assumptions, not observed facts |
| [`hackathon.md`](hackathon.md) | Slice-by-slice build log and conventions |

## Contributing

- Backend owns `src/swapdesk/` and `tests/`. Frontend owns `frontend/`.
- Keep tests deterministic; business logic stays callable without HTTP or a model.
- Record each slice in `hackathon.md` with the exact commands run and pass/fail counts.
- Never commit `.env`, databases, or real customer data. `.env.example` carries key names only.

## License

No license chosen yet. Do not reuse this code until the owners add one.