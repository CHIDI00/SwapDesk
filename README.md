# SwapDesk

SwapDesk is an autonomous state-machine for e-commerce customer support. While our current demo uses a synthetic footwear brand as a proof-of-concept, the underlying architecture is vertical-agnostic. The agent independently verifies store policy and inventory, reserves replacements, processes returns, and generates shipping labels. Every request deterministically results in an arranged exchange, a request for clarification, a policy denial, or a human escalation.

Demo Scope: Built for neatHack by a team of four, this MVP uses 100% synthetic data. No real payments, active shipments, or actual customer information are used in this demonstration.

## Repository layout

```text
frontend/          Next.js dashboard — standalone client-side demo (no backend required)
src/swapdesk/      Python backend package — FastAPI, SQLite, LangGraph agent
eval/              Frozen benchmark, deterministic checker, and run harness
tests/             Deterministic pytest suite (no network, no model)
docs/              Build plan, runbooks, evidence, and business deliverables
hackathon.md       Incremental build log and team conventions
```

## The two halves

- **Backend** (`src/swapdesk/`) — the agent runtime. Policy checks, atomic stock reservation, idempotent operations, an append-only action journal, a LangGraph tool-using agent, and a FastAPI surface for frontend integration. Deterministic and network-free to test.
- **Frontend** (`frontend/`) — the ops dashboard (Mission Control, Inbox, Inventory, Integrations, Customer Simulation, ticket detail). It is a **self-contained client-side demo** powered by a mock store — it demos the SwapDesk experience without calling the live API. Its own README lives at [`frontend/README.md`](frontend/README.md).

---

## What was planned

The build ran in order: tool setup and a test commit, then the mock shop and checker before the agent, then a first working version with a measured baseline. After that came injected failures, trace reading, fixes, and a re-run for before-and-after numbers, followed by the business plan, a demo screen, and repo cleanup, ending with the video. Full spec in [`docs/build-plan.md`](docs/build-plan.md) — a plan, not evidence of what happened. What actually happened lives in [`hackathon.md`](hackathon.md).

---

## How the three required tools fit

- **neatlogs** records every agent run: workflow and tool spans, latency, tokens, cost. Local capture works without a key; export needs `NEATLOGS_API_KEY`. Verify with `uv run python -m neatlogs doctor --local` and read back single traces with `trace get`. The agent can also query traces itself through the neatlogs MCP server.
- **Entire** captures the context behind each commit (prompts, decisions, changes) as checkpoints. It does not prove correctness; the deterministic checker does that. Checkpoints are the paper trail for the demo's fix story.
- **cfo.ai** holds the pricing, cost, revenue, and runway model. All figures there are assumptions under test, not observed facts. See [`docs/business/`](docs/business/) and the assumptions section below.

---

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

### Run the API and worker

```bash
uv run uvicorn swapdesk.api:app --port 8000
uv run python -m swapdesk.worker
```

Both share `SWAPDESK_DB` (default `swapdesk.db`); agent checkpoints live
at `<db>.agent-checkpoints.sqlite`. Interactive docs at
`http://127.0.0.1:8000/docs` (generated from the implementation, always
in sync). Normative customer contract:
[`docs/API_CONTRACT.md`](docs/API_CONTRACT.md).

| Method & route                         | What it does                                              |
| -------------------------------------- | --------------------------------------------------------- |
| `POST /v1/agent/tickets`               | Accept an agent ticket, queue RUN-1, return 202 + status URL |
| `GET /v1/agent/cases/{id}`             | Execution status + verified outcome when available (404 unknown) |
| `GET /v1/agent/cases/{id}/timeline`    | Sanitized action/journal events with run ids (404 unknown) |
| `POST /v1/agent/cases/{id}/continue`   | Queue a continuation run, or report terminal unchanged (404/409/422) |
| `POST /v1/tickets`                     | Legacy deterministic demo path (201, benchmark use; frontend must not use it) |
| `GET /v1/cases/{id}`                   | Legacy deterministic status (frontend must not use it)    |
| `GET /v1/cases/{id}/timeline`          | Legacy deterministic timeline (frontend must not use it)  |
| `POST /v1/cases/{id}/continue`         | Legacy deterministic continuation (frontend must not use it) |
| `GET /v1/fixtures`                     | Synthetic orders, items, and policy for dropdowns         |
| `POST /v1/demo/faults`                 | Disabled (403) unless `SWAPDESK_ENABLE_DEMO_FAULTS=1`     |
| `DELETE /v1/demo/faults`               | Disabled (403) unless `SWAPDESK_ENABLE_DEMO_FAULTS=1`     |
| `GET /v1/health`                       | Liveness probe                                            |

`POST /v1/agent/tickets` returns **202 accepted** with `case_id`,
`run_id`, `execution_status`, and `status_url` — never a completed
outcome. `execution_status` (`queued`/`running`/`waiting_input`/
`completed`/`failed`) is distinct from the business `outcome`
(`arranged`/`clarification`/`denial`/`escalation`, null until a run
completes). Malformed requests return 422, unknown cases 404,
submission conflicts or concurrent runs 409, disabled demo controls
403. A run is bounded by `SWAPDESK_AGENT_BUDGET` provider requests and
`SWAPDESK_RUN_TIMEOUT_S` wall-clock seconds; failed runs are never
retried automatically.

`POST /v1/tickets` remains the legacy deterministic demo path used by
benchmarks. The customer frontend must use `/v1/agent/*`. The agent
route accepts optional structured order fields as request data; the
customer message remains the primary input, and consent is recorded
only when explicitly supplied.

```bash
curl -X POST localhost:8000/v1/agent/tickets \
  -H 'Content-Type: application/json' \
  -d '{"message":"Exchange item ITEM-01 for size 42","order_id":"ORD-1001","order_item_id":"ITEM-01","size":"42"}'

curl localhost:8000/v1/agent/cases/CASE-xxx
curl localhost:8000/v1/agent/cases/CASE-xxx/timeline
curl -X POST localhost:8000/v1/agent/cases/CASE-xxx/continue \
  -H 'Content-Type: application/json' \
  -d '{"message":"42 is fine","consent_size":"42"}'
```

No authentication: this is a local mock. Agent status and timeline
reads are read-only and never block on the worker.

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
npm ci
npm run dev      # http://localhost:3000
```

Other scripts: `npm run build` (production build), `npm run start`, `npm run lint`.

### Pages flow

| Route           | Page                | What it demos                                        |
| --------------- | ------------------- | ---------------------------------------------------- |
| `/`             | Mission Control     | Agent metrics + live execution queue                 |
| `/inbox`        | Inbox               | Sample ticket stream                                 |
| `/inventory`    | Inventory           | Stock levels that react to simulations               |
| `/database`     | Database Schema     | Tables the agent reads/writes                        |
| `/integrations` | Integrations        | Mock inbound webhook URLs (Zendesk, Shopify, Gorgias) — display only, no backend |
| `/settings`     | Agent Settings      | Autonomy/guardrail config UI                         |
| `/simulate`     | Customer Simulation | Inject a customer complaint into the queue           |
| `/ticket/[id]`  | Ticket Execution    | Per-ticket action timeline                           |

## Evaluation and evidence

- `eval/cases_v1.json` — frozen 30-case benchmark (`benchmark-v1`, 8 holdouts) covering arrangement, denial, clarification, and escalation, with seeded fault schedules.
- `eval/driver.py` — deterministic reference driver (not the agent) that exercises the cases.
- `eval/harness.py` + `eval/run.py` — isolated database per run; results committed to `eval/results/v1.json`.
- `src/swapdesk/checker.py` — deterministic per-outcome checks and global invariants, no LLM judge.
- `docs/EVIDENCE_RUNNER_HARNESS.md` — a controlled live BEFORE/AFTER comparison of the D1 final-sale denial evidence path.

## Documentation

| Doc                                                                  | Purpose                                                                                         |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md)                         | Normative customer frontend contract (agent async path + legacy notes)                          |
| [`docs/build-plan.md`](docs/build-plan.md)                           | Full build plan (spec, not evidence)                                                            |
| [`docs/STUDIO_VERIFICATION.md`](docs/STUDIO_VERIFICATION.md)         | LangGraph Studio runbook with evidence                                                          |
| [`docs/EVIDENCE_RUNNER_HARNESS.md`](docs/EVIDENCE_RUNNER_HARNESS.md) | Runner/harness evidence walk-through                                                            |
| [`docs/business/`](docs/business/)                                   | Business plan (MD/PDF) and financial model (XLSX) — figures are assumptions, not observed facts |
| [`hackathon.md`](hackathon.md)                                       | Incremental build log and conventions                                                           |

## Troubleshooting

- **A run hangs.** Agent executions are bounded by `SWAPDESK_AGENT_BUDGET` requests and `SWAPDESK_RUN_TIMEOUT_S` seconds, but an in-flight model call cannot be cancelled. Wait for the timeout to record failure; the case resumes cleanly and idempotency keys prevent double effects.
- **A test needs symlinks and fails with error 1314.** Enable Windows Developer Mode or run the terminal as administrator.
- **neatlogs shutdown log noise.** The SDK logs its own shutdown after stdout closes. Cosmetic; it changes no results.
- **Ports.** API `8000`, Studio server `8123`, frontend `3000`. Pick one live path per demo (scripted Studio scenarios or API demo faults, not both).

## Limitations

- Synthetic Environment: This MVP operates on a synthetic shoe-store database to prove our autonomous state-machine logic. While policies and tools are modular and swappable at the code level, this build uses simulated data with no live payments, real shipments, or active customer PII.
- Security & Auth: API authentication is intentionally bypassed to allow judges seamless access to the local evaluation mock.
- The frontend runs on a client-side mock store until Slice 5 wiring lands; dashboard numbers (e.g. completion rates) are simulated and labeled Demo Mode.
- Metrics Integrity: Dashboard metrics (like completion rates) reflect simulated data and are explicitly labeled "Demo Mode" while we finalize backend API wiring.
- Deterministic Logging: Our timeline only journals executed business actions. If an escalation legitimately requires no action (e.g., a return is out of policy), the timeline remains intentionally empty. This is a successful path, not missing data.
- State Definitions: When a ticket is marked as "arranged", it means the agent successfully verified state, reserved the replacement, created the return, and generated the label in the database. It does not imply physical fulfillment.
- Benchmarking: Our benchmark scores (based on 30 synthetic test cases) are designed to validate the agent's logic within this isolated environment, rather than claiming enterprise production reliability.

## Contributing

- Backend owns `src/swapdesk/` and `tests/`. Frontend owns `frontend/`.
- Keep tests deterministic; business logic stays callable without HTTP or a model.
- Record each change in `hackathon.md` with the exact commands run and pass/fail counts.
- Never commit `.env`, databases, or real customer data. `.env.example` carries key names only.

## License

MIT — see [LICENSE](LICENSE).
