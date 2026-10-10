# SwapDesk

SwapDesk arranges shoe exchanges for a fictional shop. A customer asks for a different size, and the backend checks policy and stock, holds a replacement, creates a return and a mock label, then verifies the saved state. Every request ends in one of four outcomes: exchange arranged, clarification required, policy denial, or human escalation. All data is synthetic. There are no payments, shipments, or real customers.

This repo holds the backend. It is a neatHack project, currently at Slice 4 of 7 (neatlogs and LangGraph agent). The HTTP API and demo do not exist yet.

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

## Configuration

- Return window and eligibility live in `src/swapdesk/policy.py` (`RETURN_WINDOW_DAYS = 30`).
- Each call takes a database path, so tests and scratch work never touch real files. There is no server config yet.
- Agent and telemetry read `.env` (git-ignored, never committed; see `.env.example` for the key names): `GEMINI_API_KEY`, `NEATLOGS_API_KEY` (both optional; without them the agent needs a passed-in model and telemetry stays local-only).
- The live model is `gemini-3.8-flash` unless `SWAPDESK_MODEL` overrides it.
- Live model and telemetry export need working egress to Google APIs; where the network blocks them, the deterministic suites still pass.

## Project structure

```text
src/swapdesk/
  db.py          SQLite schema and transactions
  models.py      Typed records, states, transitions
  policy.py      Eligibility rules
  fixtures.py    Synthetic shop data
  operations.py  reserve/return/label/finalize/release/cancel/escalate/verify
  faults.py      Demo-only failure injection (tests, never production)
  checker.py     Deterministic benchmark checker (no LLM judge)
  telemetry.py   neatlogs init/wrap/flush (local-only without a key)
  agent/
    tools.py     Curated LangChain tools bound to one case run
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
```

Build progress lives in [hackathon.md](hackathon.md). The full plan is in [SwapDesk neatHack Build Plan.md](SwapDesk%20neatHack%20Build%20Plan.md) (spec, not evidence).

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
