# Studio verification and PR evidence

## Start offline

```bash
uv sync --frozen
uv run langgraph dev
```

Open the Studio URL printed by the server; it includes the actual host and port.
Choose **swapdesk_offline** and submit:

```json
{"scenario": "arrange", "resume": false}
```

Other scripted scenarios are `deny` and `recover`. Fresh automatic identities create a new synthetic case database, including on repeated fresh submissions to a persisted thread. Explicit IDs remain supported; an existing explicit case without resume errors instead of resetting it. Cases created before identity manifests were added need a fresh case ID. IDs accept letters, digits, underscores and hyphens only, and paths stay inside the configured Studio root.

## What should be visible

The graph is `prepare → agent → verify`, with explicit error paths. The production agent is registered as a compiled subgraph. Expand it to see **model ↔ tools**, then inspect full messages for tool arguments and results. Individual tools share a tools node; the execution trace identifies each actual call.

Offline scripts replay predetermined calls through production tools and real SQLite operations. They do not interpret arbitrary customer messages or choose from tool results. They prove wiring and backend effects, **not Gemini decision quality**. Customer replies are generated only from persisted terminal case state. Error runs expose diagnostics without a customer reply or claimed outcome; stale success fields are cleared.

## Resume

The serving platform supplies the parent checkpointer. Inner messages and script position share its checkpointed state. Continue an interrupted execution on the **same Studio thread**, without replacing it with a fresh input run. In Python use `graph.invoke(None, config)` with the original thread ID. Regression tests interrupt after tool steps and prove that continuation does not replay completed reservations.

For an explicit continuation of a completed thread, preserve its returned case ID, run ID and scenario:

```json
{"scenario": "arrange", "case_id": "COPY-RETURNED-CASE-ID", "run_id": "COPY-RETURNED-RUN-ID", "resume": true}
```

This is not a new scripted scenario. For a new test submit `resume: false`, normally on a new thread. Automatically assigned identities are refreshed on fresh submissions on a persisted thread as well.

## Live request ceiling

**swapdesk_live** is opt-in. It requires `SWAPDESK_MODEL`, a securely configured `GEMINI_API_KEY`, and a positive integer budget. Never paste credentials into messages.

```json
{"message": "Exchange ITEM-01 on order ORD-1001 for size 42.", "budget": 2, "resume": false}
```

The budget is a **cumulative generation-attempt ceiling per original case/run**, not a new allowance on resume and not a global account quota. `requests_spent` is reserved atomically in SQLite before generation, including failed attempts. Raising the ceiling on resume explicitly permits additional attempts. Separate fresh cases have separate budgets. A crash after reservation may conservatively count an attempt that never reached the provider.

Sync, async and streaming request paths are capped. SDK retries are forced to one attempt, including call-level overrides. Configuration/budget/model errors terminate with partial-state diagnostics, not an invented escalation or success reply.

## Test evidence and limitations

Based on `c292cfce24854fb5890b4ff407a1e2d0a65e7b9b`.

- `uv sync --frozen`: completed with the existing lock, unchanged.
- Baseline `SWAPDESK_TELEMETRY_ENV=0 uv run pytest -q`: **57 passed**.
- Final same command: **86 passed in 20.91s**; 29 added test cases.
- Tests cover recursive subgraph discovery, fresh persisted-thread runs, stale success clearing, safe paths, consent context, interrupted continuation, atomic budgets, mocked sync/async/streaming transports, retry configuration and failed-attempt accounting.
- One new development assertion was corrected to expect namespaced xray nodes (`agent:model`, `agent:tools`); existing tests were not weakened.
- Tested frozen versions: Python 3.12.15, LangChain 1.4.4, LangGraph 1.2.14, langchain-google-genai 4.4.0, google-genai 2.29.0, langgraph-api 0.10.3 and langgraph-cli 0.4.33.

**Zero live Gemini requests. Browser Studio rendering and live Gemini behavior remain unverified and require local user checks.** Frozen benchmark data, holdouts, backend policy and Slice 5 remain unchanged. No framework migration or auto-merge.

**Entire disclosure:** this Ari authoring session was not Entire-captured. Existing `.entire` settings, historical logs and checkpoint artifacts remain untouched. No checkpoint trailer was fabricated and no history was rewritten.
