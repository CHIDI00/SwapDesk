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
