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
