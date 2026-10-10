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

- Python with uv, FastAPI, Pydantic, SQLite, pytest, LangGraph, neatlogs (planned, not yet installed)
- cfo.ai workspace: SwapDesk, org_id 102985 (read-only for backend work; no model changes)
- Entire 0.11.4 with OpenCode plugin (this session)

## Build log

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

- No backend code yet; Slice 1 is next.
- Entire checkpoint linkage not yet verified for this session.
- cfo.ai pricing model not built; no runtime integration claims.
- Submission requirements to be rechecked against published pages before submission.

## Submission

Confirmed: none yet. Outstanding: rules recheck, public repo evidence, video, X post. Nothing published or submitted.
