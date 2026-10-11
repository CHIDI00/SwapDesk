# hackathon.md

## Project

SwapDesk: an exchange agent for a fictional shoe shop. One item per request; outcomes are exchange arranged, clarification required, policy denial, or human escalation. Synthetic data only.

## Team

- Adrien Oke, AI Engineer (backend scope this session)
- Joshua Onyeka, Frontend Engineer
- Ituma Chidi, Frontend Engineer
- Emmanuel Makanjuola, Backend Engineer

Contact details shared in chat are withheld from this public log.

## Stack

- Python with uv, FastAPI, Pydantic, SQLite, pytest, LangGraph, neatlogs (all installed; see pyproject.toml and uv.lock)
- cfo.ai workspace: SwapDesk, org_id 102985 (business model built there; backend reads nothing from it at runtime)
- Entire 0.11.4 with OpenCode plugin (this session)

## Build log

### 2026-10-11 - MIT license confirmed

Completed:

- `LICENSE` verified MIT (SwapDesk contributors, 2026). `README.md` License section already points to it. `pyproject.toml` carries no license field; no change needed for submission.
- Outstanding license item closed; history entries noting "unchosen" left intact.

Tests run: none (docs only).

Failures: none.

### 2026-10-11 - README and submission docs finalized (no slice language)

Completed:

- README: full layout including root files; new "What was planned" and "How the three required tools fit" sections; Docker/Render setup marked reviewed-but-undeployed; integrations row labeled mock; `npm install` corrected to `npm ci`; new Troubleshooting, Limitations, and pending Submission status sections. All slice wording removed (verified zero matches).
- `hackathon.md` stale summaries refreshed (stack, limitations, submission); history preserved untouched.
- CFO files checked without changes: business MD carries no links, workspace access, or share URLs; pricing ($49/100/$0.50), $15k opening cash, and scenario figures stay labeled assumptions; PDF/XLSX not re-diffed here (prior byte scan plus headline match stands).
- Event page rechecked Oct 11: weights 30/25/20/15/10; submission Oct 12 7:00–11:55 PM IST via X quote-post; cfo.ai signup card-then-cancel note; LiteLLM $20 shared budget. Unconfirmed items stay pending.
- Audit script not run (no Ruby on this machine); checklist applied by hand. License still unchosen per instruction.

Tests run: none (docs only).

Failures: none.

### 2026-10-11 - Frontend integration reads plus deployment hardening

Completed:

- `GET /v1/agent/cases` (inbox list): durable agent-path cases newest first with unique `(created_at, case_id)` keyset cursor, validated `execution`/`outcome` filters (422 otherwise), `limit` default 25 max 100, `items`/`next_cursor`/`total`/population-wide `summary`. Every item reuses the detail resolver, so list/detail agree including the 0d8c55a run-outcome fallback; customer messages are credential-scrubbed. Read-only: SELECTs only, no model calls.
- `GET /v1/inventory`: actual stock by SKU/size with `available = on_hand - held`, exact-match filters, `limit` default 100 max 500, stable `(sku, size)` ordering. Proven read-only: a solo call on a fresh database returns empty and leaves no tables behind (no seeding, no reservation movement). No warehouse/product fields invented.
- `GET /v1/ready`: queue-state deployment signal (`queued_depth`, `oldest_queued_age_s`, `last_terminal_at`) documented as not proof of worker life; `/v1/health` stays liveness-only.
- Deployment (on Emmanuel's Docker files, additive only): entrypoint rewritten so either child exiting terminates and reaps the other with the first status propagated, TERM/INT reaches both, 10s-bounded KILL escalation, plus `SWAPDESK_WORKER_CMD`/`SWAPDESK_API_CMD` overrides for testing. `uv` image pinned to locally verified `0.10.8` (was `latest`). `.dockerignore` now excludes `.env*`/`*.pem`/`*.key`; `.gitignore` gains `.env.*` while keeping `.env.example` tracked; `.langgraph_api/` ignore entry verified present. API/worker/checkpoints share `SWAPDESK_DB`'s directory by construction; empty-volume startup seeds nothing on reads and marks interrupted runs failed without replay (existing behavior, covered).
- Access posture analyzed, nothing changed: CORS is not auth, per-run caps don't bound aggregate spend, secrets stay server-side, demo faults disabled. Recommendation recorded in `docs/API_CONTRACT.md` (platform gate or admin key + rate limits before public paid intake). Nothing deployed.
- Contract examples published in `docs/API_CONTRACT.md` for frontend sign-off (list, inventory, readiness, access note). Hard-coded shoe-shop policy untouched; no new integrations; no agent-reasoning changes.

Tests run: `uv run pytest tests/test_agent_reads.py -q` (8 passed: lists/filters/pagination/summary, list/detail agreement, escalation-without-state, inventory before/during/after finalize, read-only repeats, sanitization, readiness/access basics, OpenAPI coverage, entrypoint supervision with fake children under Git bash); `uv run pytest -q` (144 passed, 1 skipped), locked `uv` environment, zero paid calls. `docker build` unverified (Docker CLI present, daemon not running). TERM/INT supervision path documented, POSIX-only test skipped on win32.

Failures: two implementation bugs found by the new tests same session — keyset cursor unpacked 2 parts into 3 names (every `next_cursor` unusable; fixed), and the entrypoint test resolved `bash` to the System32 WSL relay stub (fixed by preferring a verified Git bash and pinning it on PATH).

### 2026-10-11 - Explicit model spans for the LiteLLM-proxy path

Completed:

- Locked-SDK audit (neatlogs 1.4.26): `wrap()` documents raw OpenAI clients only; LangChain `ChatOpenAI` fell into the generic `openai`-module branch whose patches never fire on langchain's own HTTP layer. That explains the boot-check trace (`608bd91b…`) recording `llm_calls: 0` despite a completed run. No auto-capture exists for this path.
- New `src/swapdesk/agent/model_spans.py`: `InstrumentedChatOpenAI` emits exactly one explicit LLM span per generation (`_generate`/`_agenerate`/`_stream`/`_astream`), with model name, sanitized input/output (credential patterns scrubbed, 4k truncation), latency, provider-returned usage when present and omitted when absent (unknown, never zero), and error type with re-raise. Wired into the LiteLLM branch of `build_model`; Gemini path untouched.
- `telemetry.maybe_wrap_provider` now returns wrap-unsupported subclasses unwrapped instead of raising `TypeError` (explicit spans are the single counting point there). Found via the existing `test_wrap_covers_openai_client` failing honestly after the wiring; fixed same session.
- New `tests/test_model_spans.py` (7 tests, fake provider through the real adapter, zero network, ~2s): one-span-per-generation with preserved usage, unknown-not-zero omission, error recording plus re-raise, secret scrubbing, single streaming span, instrumented client construction, and real-SDK acceptance of the span shape.

Tests run: `uv run pytest tests/test_model_spans.py tests/test_provider.py -q` (12 passed); full `uv run pytest -q` (134 passed, 1 skipped), locked `uv` environment, no paid calls.

Failures: one regression same session (`test_wrap_covers_openai_client` → `TypeError` from `wrap()` name matching on the new subclass), fixed by documented unwrapped return.

### 2026-10-11 - Reconciled async agent queue on the existing agent service path

Completed:

- Reconciled the `feat/api-agent-queue` queue/worker work against current `origin/main` with no force-reset and no teammate changes discarded. Emmanuel's `submit_agent_ticket()`, structured `AgentContext` fields, case-specific checkpoint threads (`case_id:run_id`), and database-derived verification are kept as the one agent execution implementation; the worker invokes it per claimed run with the run's saved request.
- Ported durable `submissions`/`runs` records (`src/swapdesk/queue.py`): requests persisted before execution, atomic single-worker claiming with no concurrent runs per case, submission idempotency (same key/payload returns the case, same key/different payload is 409), interrupted runs marked failed on startup with no blind replay and no automatic retry of paid executions.
- `src/swapdesk/worker.py` executes each claimed run exactly once through `service.submit_agent_ticket()` (extended additively with `run_id`/`model`/`middleware` passthrough; defaults unchanged). RequestBudget middleware from the feature branch is wired into every run so actual provider requests are capped (`SWAPDESK_AGENT_BUDGET`, default 12); recursion limits remain as loop bounds only. Explicit wall-clock timeout (`SWAPDESK_RUN_TIMEOUT_S`, default 300) with documented cancellation limits: in-flight model calls cannot be cancelled, late commits are idempotent by operation key, and timeouts queue no retry.
- Customer contract: `POST /v1/agent/tickets` is now async 202 with `case_id`/`run_id`/`execution_status`/`status_url`; `GET /v1/agent/cases/{id}` and `/timeline` expose saved progress with run ids; continuation runs the same agent path and terminal cases return saved results with no model call. `/v1/tickets` and `/v1/cases/*` stay byte-compatible as the documented legacy deterministic path. Exact request/response examples published in `docs/API_CONTRACT.md` for frontend integration, with the 201-completed to 202-accepted change called out.
- Narrowed the stock clarification guard to questions that actually assert unavailability (out-of-stock/unavailable/sold-out phrasing); other clarifications record normally when inventory is available. Emmanuel's out-of-stock regression test still passes; a non-stock clarification case is added.
- `/v1/demo/faults` now returns 403 unless `SWAPDESK_ENABLE_DEMO_FAULTS=1`; customer execution never depends on it. Development CORS added for the actual frontend origins (`http://localhost:3000`, `http://127.0.0.1:3000`, override via `SWAPDESK_CORS_ORIGINS`).
- Emmanuel's `/v1/agent/tickets` sync tests were adapted to the async flow with identical intent (clarify then continue to arranged; config failure loud without fallback; early failure then explicit continuation). His fault-recovery test now enables the demo flag explicitly.

Tests run: `uv run pytest tests/test_agent_queue.py -q` (13 passed, injected scripted models, zero paid calls); `uv run pytest tests/test_api.py tests/test_agent.py tests/test_provider.py -q` (33 passed); full `uv run pytest -q` (125 passed, 1 skipped) using the locked `uv` environment. Worker boot verified (`uv run python -m swapdesk.worker` prints ready line; killed on timeout as it polls forever). No environment blockers encountered in this session.

Failures: none in the reconciled path. One test-adaptation round (agent route sync doubles needed `**kwargs` for the new middleware passthrough; fault tests needed the explicit demo flag).

Gaps (explicitly pending):

- No paid live-model run through the queue; production path proven with injected doubles only.
- Frontend still on the client-side mock store; integration against `docs/API_CONTRACT.md` pending with Joshua/Chidi.
- Single local worker only; no auth, no multi-worker, no retry/backoff beyond explicit continue.

### 2026-10-11 - Expose the checkpointed agent through the API

Completed:

- Added `POST /v1/agent/tickets` as an opt-in natural-language path to the existing LangGraph agent; the deterministic `POST /v1/tickets` demo path is unchanged.
- Agent requests accept optional structured order hints, use the SQLite checkpoint alongside the configured business database, and return verified database-derived outcomes and replies.
- Caller-provided case IDs support explicit `resume=true` retries after execution failures, including failures before any business operation was written. Provider configuration errors return 503; execution failures return 502 with the case ID needed to resume.
- Namespaced LangGraph checkpoint threads by case and run, preventing two tickets with the same run ID from sharing conversation state.
- Live HTTP testing found the model claiming an available size was out of stock. Agent tools now receive structured order/item/size/quantity context and reject that unsupported clarification when saved policy and inventory show the request is eligible and available; the model then continued through the normal exchange flow.
- Documented the agent endpoint and request example in the README.

Tests run: full deterministic backend suite → 111 passed, 1 deselected (`neatlogs` doctor requires the locked SDK version). Tests ran under Python 3.14 with process-local telemetry compatibility shims because `.python-version` specifies 3.12, the available `.venv` is 3.14, and the installed `neatlogs` 1.1.8 lacks APIs required by the lockfile version 1.4.26. Live HTTP smoke test against the configured model provider used synthetic data and arranged an exchange with one reservation, return, label, and finalize event.

Failures: initial environment-only test failures due to incompatible Python/dependency setup; resolved for the deterministic suite with test-process-only shims. Initial live model run made an unsupported out-of-stock claim, now blocked by the backend guard and covered by a deterministic regression test. No repository dependency or lock files changed.

### 2026-10-10 21:45 +01:00 - cfo.ai draft business-plan deliverable complete

Completed:

- Added supplier-built cfo.ai outputs byte-identical to `docs/business/`: [SwapDesk-Business-Plan.md](docs/business/SwapDesk-Business-Plan.md), [SwapDesk-Business-Plan.pdf](docs/business/SwapDesk-Business-Plan.pdf), [SwapDesk-Financial-Model.xlsx](docs/business/SwapDesk-Financial-Model.xlsx). No numbers regenerated or changed.
- Model covers Base (Main-Scenario), Growth, and Bad Reliability scenarios over October 2026–September 2028. Pricing ($49/store/month incl. 100 verified arrangements; $0.50 per extra), growth, support time, and $15,000 opening cash are assumptions, not observed facts. Hackathon credits excluded from recurring economics.
- Reviewed all three files for sensitive content: no emails, phone numbers, API keys, or credentials found (byte scan of PDF/XLSX, full read of MD). Headline figures in the workbook match the MD summary.
- No claim made of profitability, validated demand, or production reliability: Main-Scenario ends at ($588) operating profit, demand/pricing unvalidated per the plan itself, and live benchmark/model-decision gaps remain open (see runner/harness evidence entry).

Gaps (explicitly pending):

- cfo.ai account/card step, business-plan submission file packaging, video, X post.

Tests run: none (documentation packaging only).

Failures: none.

### 2026-10-10 20:50 +01:00 - Runner/harness evidence saved for submission

Completed:

- Evidence doc `docs/EVIDENCE_RUNNER_HARNESS.md`: controlled 2-run live comparison of the D1-final-sale denial evidence path. BEFORE (controlled reproduction, trace `79a02458…`) loses the persisted reason (`expected message containing 'final sale', got ''`); AFTER (trace `8d4b7cc8…`) preserves it, checker passes, zero side effects in both. Diagnostic trace `0b32a1f5…` retained as reference. Fix commit `90c89d8`, checkpoint `01M4KJS2K88G9T2AWH11WVZG44`. Runner/harness correctness only; no model-reasoning claim.
- Sanitized: trace IDs plus synthetic fixture data only. No credentials, keys, session transcripts, temp worktrees, databases, or experimental code committed.

Gaps (explicitly pending):

- No full 42-run re-baseline; V1/V2 scores provisional. Recovery paths and model decision errors (v2 A13/C3) uncovered. No video, X post, or submission artifacts.

Tests run: none (packaging only; prior deterministic suite 106 passed, 1 skipped).

Failures: none.

### 2026-10-10 09:00 +01:00 - Anthropic removal, commit convention, Gemini key test

Completed:

- Anthropic endpoint fully removed from the repo: no code/config references it (grep clean across `src/`, `eval/`, `tests/`, `.opencode/`, `opencode.json`, `README.md`, `pyproject.toml`); orphaned `anthropic` package dropped via `uv sync`. One inert transitive shim remains (`openinference-instrumentation-anthropic`, required unconditionally by `neatlogs` itself): no endpoint, no credentials, never imported. Suite still 46 passed.
- Convention recorded (user instruction): no "slice" in commit messages going forward. Past messages keep their history (rewriting would break Entire checkpoint linkage).
- Gemini key test, max two API calls, values never printed: CALL1 raw ping → error `ConnectError [SSL: UNEXPECTED_EOF_WHILE_READING]` at the TLS handshake; CALL2 correctly skipped, one call spent. Verdict: error at the network layer, key itself unevaluated. Dashboard check is moot until egress works.

Gaps:

- `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_BASE_URL` still exist in the machine's shell environment (outside the repo, nothing reads them). Removing them is a machine-level action for the user.
- Live Gemini + neatlogs export still unverified from here; needs working egress, then a dashboard confirmation.

### 2026-10-10 08:54 +01:00 - Local Studio server running

Completed:

- Added a Studio entrypoint (`src/swapdesk/agent/studio.py`, exact production wiring, local stand-in model) plus `langgraph.json`. Graph compiles offline with no database side effects.
- Installed `langgraph-cli[inmem]` pinned below 0.4 as a dev dependency. The current CLI release would not resolve: `neatlogs` pulls `autogen-core`, which caps protobuf below 5.30, while the new server needs protobuf 6.32 or higher.
- Narrowed `neatlogs[anthropic,google-genai]` to `neatlogs[google-genai]`. This also drops the last Anthropic packages from the environment. Suite still 46 passed.
- Fixed a server startup failure: Studio loads the entrypoint without package context, so the entrypoint now uses absolute imports. Server auto-reloaded and registered the `swapdesk_agent` assistant.
- Server: API `http://127.0.0.1:8123`, docs `http://127.0.0.1:8123/docs`, Studio `https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:8123`.

Planned:

- Live runs from Studio still need `SWAPDESK_MODEL` in `.env` plus working egress to Google APIs. The stand-in only draws the graph.

Tests run: `uv run pytest -q` (46 passed, same known shutdown log noise).

Failures: two setup failures, both fixed same session (missing `inmem` server package; relative import in Studio entrypoint).

### 2026-10-10 08:32 +01:00 - Slice 4: neatlogs and LangGraph agent done

Completed:

- Provider is Gemini (user-confirmed; `.env` carries `GEMINI_API_KEY` + `NEATLOGS_API_KEY`, names only, values never touched). Dropped the unused `langchain-anthropic`.
- Deps via uv: `langchain` 1.4.4 (new `create_agent`, not deprecated `create_react_agent`), `langgraph` 1.2.14, `langchain-google-genai`, `langgraph-checkpoint-sqlite` 3.1.1, `neatlogs` 1.4.26. `uv.lock` committed.
- New modules (business logic untouched): `telemetry.py` (dotenv loader, once-only init, local-only without key, Gemini wrap), `agent/tools.py` (14 curated tools, structural key discipline, JSON errors with retry flags), `agent/prompts.py` (system prompt + DB-rendered reply templates), `agent/graph.py` (`create_agent` wiring, recursion-bounded runs, file checkpointer separate from business data, DB-derived outcomes).
- Agent rules hold: one loop chooses tools from results; resume reuses keys; op-status query after uncertain writes; untrusted input; no silent substitution; reply from verified state (fake tracking in model text provably excluded).
- Tests: `uv run pytest -q` → 46 passed (12 new agent tests, scripted model, zero API spend). Five honest failures fixed same session (moved `BaseChatModel` import, iterator-only fake model, missing sqlite row factory, duplicate tool-call ids, sqlite thread guard).
- `neatlogs doctor --local` passes. Export path implemented but unproven from here.

Gaps (explicit, blocking nothing deterministic):

- Live Gemini unreachable from this machine (TLS EOF to Google APIs; Anthropic endpoint also TCP-dead). No live model listing, no live smoke run. `SWAPDESK_MODEL` is required with no guessed default.
- neatlogs export/dashboard unverified: key exists in `.env`, but egress fails here. Needs a networked run plus user dashboard confirmation.
- Agent baseline on frozen cases is Slice 6 work; holdouts stay excluded from tuning.

Planned:

- Slice 5: FastAPI routes for frontend teammates.

Tests run: `uv run pytest -q` (46 passed); `neatlogs doctor --local` (pass).

Failures: five development failures above, all fixed same session.

### 2026-10-10 08:03 +01:00 - Slice 3: independent checker and frozen benchmark done

Completed:

- `src/swapdesk/checker.py`: deterministic checks, no LLM judge. Per-outcome rules (arranged exactly-one-effect + truthful handoff + exact stock consumption; denied/clarification zero-writes + reason/question match; escalated partial-state accuracy + cleanup done/pending/none) plus global invariants (reference data frozen, nonnegative inventory, hold reconciliation, journal linkage, only the case's pools move) and run-log truthfulness.
- `eval/cases_v1.json`: 30 frozen cases (`benchmark-v1`), seeded fault schedules, 8 holdouts (A3, A7, A11, S1, D2, C3, C5, E1), 6 cases repeated 3 times (42 runs total: 15 arranged, 4 denied, 5 clarification, 6 escalated). Expected answers live only here; the future agent never sees this file.
- `eval/driver.py`: deterministic reference policy (fixed templates, bounded same-key retries, abandonment/escalation paths, rerun/cross-case/cancel-fresh/cross-run scripts). Not the agent.
- `eval/harness.py` + `eval/run.py`: isolated DB per run, committed evidence `eval/results/v1.json` (42/42 passed).
- Reserve records `requested_size` separately from authorized `size` (consent cases); fixture adds shipped `ITEM-08`/`ORD-1006`. README slice pointer/structure refreshed; snippets re-verified verbatim.
- Tests: `uv run pytest -q` → 34 passed (8 + 13 + 11 checker mutations + 2 freeze). Three honest failures fixed same session: invariant read `sku_hint` instead of `sku`; checker never parsed `progress_json` (consent notes invisible); driver lumped mismatch with unknown-item and lost the original requested size.

Planned:

- Slice 4: neatlogs + LangGraph agent against these frozen cases (holdouts excluded from prompt tuning).

Tests run: `uv run pytest -q` (34 passed); `uv run python eval/run.py` (42/42).

Failures: three development failures above, all fixed same session.

### 2026-10-10 07:37 +01:00 - Slice 2: complete mock exchange done

Completed:

- New tables `returns`, `labels`, `cases`; `exchanges.hold_released`; unique index now excludes `arranged`/`escalated` too. Exchange transition map enforced (`replacement_reserved` → `return_created` → `label_created` → `arranged`, with `cleanup_pending`/`escalated`/`denied`/`cancelled` escapes).
- New ops: `create_return`, `create_label`, `finalize_arranged` (consumes hold into mock shipment), `release_reservation` (idempotent, never double-decrements), `cancel_exchange` (cancelled allows a fresh exchange id), `escalate_case` (reason required), `note_case`/`get_case` progress, read-only `verify_exchange` handoff (`suggested_next`, consistency flags).
- `faults.py` (demo-only controls): transient, stock-deplete, post-commit crash/timeout, release-fail. Failed cleanup persists `cleanup_pending` and stays visible; same-key retry updates the op row instead of double-inserting.
- Safety: fresh key after a committed step is rejected (re-query + reuse original key); arranged/escalated duplicates reuse the finished exchange; release after release is a recorded no-op.
- Tests: `uv run pytest -q` 3 runs, 21 passed each (8 Slice 1 + 13 Slice 2). Two honest failures fixed same session: missing `OP_RELEASE` import; UNIQUE violation on same-key retry after failed cleanup (now UPDATEs the op row).
- No new dependencies (stdlib + pytest only). No agent yet (Slice 4); neatlogs not installed (Slice 4).

Planned:

- Slice 3: deterministic checker + frozen ~30-case benchmark (no LLM judge).

Tests run: `uv run pytest -q` (3 runs, 21 passed each).

Failures: two development failures above, both fixed same session.

### 2026-10-10 07:09 +01:00 - Slice 1 commits re-attached to Entire checkpoints

Completed:

- `4c298c3` (Slice 1) and `5beae0c` (README) had no Entire checkpoint (`checkpoint explain` → "not created during an Entire session"). Per explicit user instruction, soft-reset to `62b1da7` and recommitted byte-identical trees as `ed0eb54` and `dfac87e` through this captured session (`git diff 5beae0c --stat` empty after; build plan left untracked; nothing pushed).
- New checkpoints: `01M4J6SB1Z196SK1RN9JCC7E8R` → `ed0eb54` (session `ses_edbbdf…`, author, transcript captured); `01M4J6T16TESM6A3GTWW982RJ9` → `dfac87e`. Old SHAs remain recoverable via reflog/Entire refs.
- Tests: `uv run pytest -q` → 8 passed after the recommit.

Failures: none in the recommit; prior gap (commits made outside a captured session) now closed.

### 2026-10-10 06:54 +01:00 - Slice 1: reservation foundation done

Completed:

- `uv init --lib` plus `uv add --dev pytest`. Stack is stdlib SQLite plus pytest; FastAPI, LangGraph, and neatlogs stay out until their slices.
- New code in `src/swapdesk/`: `db` (schema, WAL, IMMEDIATE transactions), `models` (typed records), `policy` (30-day delivered window, final sale excluded), `fixtures` (synthetic shoe shop, 5 orders, 7 items), `operations` (`reserve_replacement`, `get_operation_status`, read helpers).
- One transaction commits the stock hold, exchange row, idempotency record, and journal event together. Same key plus same payload returns the saved result; same key plus different payload raises. A second key for an item with an active exchange reuses it as a duplicate with no new stock effect. Exact requested size only, no substitution.
- `.gitignore` now ignores local runtime databases (`*.db`, `*.sqlite`, `*.sqlite3`).
- Tests: `uv run pytest -q` gives 8 passed, repeated 3 times (24/24). Proofs cover eligible success, same-key idempotency, payload mismatch rejection, ineligible and insufficient-stock runs leaving inventory and tables untouched, distinct cases sharing one exchange, 5-thread oversell test on 2 units, and nonnegative inventory with journal linkage.
- First concurrency draft failed honestly (8th test): one item allows only one active exchange, so 2 units could not be taken twice. Fixed the test by adding a second item on the same SKU/size pool, not by weakening the rule.

Planned:

- Slice 2: return creation, label creation, reservation release, workflow progress and state transitions, failure injection and recovery.

Tests run: `uv run pytest -q` (3 runs, 8 passed each).

Failures: one test design failure during development (see above), fixed same session.

### 2026-10-10 06:58 +01:00 - README rewritten

Completed:

- Replaced the one-line README with onboarding docs: value prop, install, runnable quickstart, config, structure, testing, contributing, license placeholder. No emojis.
- Verified both usage snippets run verbatim against a scratch database (since deleted). Clone URL matches `origin`.
- Could not run the skill audit script: Ruby is not installed on this machine, so the checklist above was applied by hand instead.

Planned:

- Choose a license before anyone reuses this code.
- Revisit README in Slice 5 when real API routes exist.

### 2026-10-10 06:48 +01:00 - Milestone 1: Entire session capture verified end-to-end (prior session)

- Goal: verify Entire agent capture works before feature development.
- Root cause found: the Entire OpenCode plugin spawns hooks via `sh -c` (`command -v entire` guard). `sh` was not resolvable in the plugin process PATH on this machine (only `C:\Program Files\Git\cmd` is on the default PATH; `sh.exe` lives in `C:\Program Files\Git\usr\bin`). Node/Bun `spawn("sh")` returned `ENOENT`; the plugin swallows spawn errors, so every hook silently failed and no session state existed (0 sessions, 0 checkpoints).
- Fix (applied): installed Git's real `sh.exe` plus `msys-2.0.dll` into `C:\Users\DELL\.local\bin`, which is on the running OpenCode CLI PATH, so no restart was needed.
- Verified: `command -v entire` resolves and `entire session list` shows an active session created by a real `turn-start` hook. Checkpoint 01M4J5NZTH30SEH3EYT3QK1RZC links commit 622e840.
- Rule carried forward: if capture ever stops, stop and fix. A commit without linked session context is not evidence of capture.

### 2026-10-10 06:50 +01:00

Completed:

- Read repo state: README, Build Plan, opencode.json, .gitignore. No AGENTS.md, no hackathon.md, no Python project yet.
- Loaded neathack skill from `.opencode/skills/neathack/SKILL.md`.
- Recorded user-reported organizer authorization to start building (user statement; not verified against published start time; commit timestamps unaltered).
- Entire check: enabled on branch main, OpenCode agent installed, `sh` resolves in this session, 1 active session. No restart needed. One earlier checkpoint is local only and was not pushed.
- Agreed: backend lives in `src/swapdesk/`; no ICM workspace scaffolding (code only); smoke-test commit approved.
- Created this file. Team contact details (emails, phones) were provided in chat and deliberately left out of this public file.

Planned:

- Entire smoke-test commit of this file only, then checkpoint linkage check.
- Slice 1: fixtures, persistence, reserve_replacement, operation status, journal, tests via `uv run pytest`.

Tests run: none yet.

Failures: none yet.

## Demo

Pending. No URL.

## Known limitations and next steps

- Live model and deploy paths verified only where the log says so; egress and hosting gaps are recorded per entry.
- cfo.ai figures are assumptions under test, not observed facts.
- Submission requirements rechecked against the published pages on Oct 11 (weights 30/25/20/15/10; cutoff Oct 12 7:00–11:55 PM IST; video and X quote-post pending).

## Submission

Confirmed: nothing submitted. Outstanding: video (3 min or less, all three tools), X quote-post, cutoff Oct 12 7:00–11:55 PM IST, team publication names. License: MIT done. Nothing published, deployed, or submitted.
