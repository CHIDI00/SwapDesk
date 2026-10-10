# SwapDesk — neatHack build log

Authorization to start is user-reported (hackathon organizers authorized). Project scope: one item per request; outcomes are exchange arranged, clarification, policy denial, or escalation. No refunds, real shipping, payments, or customer data.

## 2026-10-10 — Milestone 1: Entire session capture verified end-to-end

- Goal: verify Entire agent capture works before feature development.
- **Root cause found:** the Entire OpenCode plugin spawns hooks via `sh -c` (`command -v entire` guard). `sh` was not resolvable in the plugin process's PATH on this machine (only `C:\Program Files\Git\cmd` is on the default PATH; `sh.exe` lives in `C:\Program Files\Git\usr\bin`). Node/Bun `spawn("sh")` returned `ENOENT`; the plugin swallows spawn errors, so every hook silently failed and no session state existed (0 sessions, 0 checkpoints).
- **Fix (applied):** installed Git's real `sh.exe` + `msys-2.0.dll` into `C:\Users\DELL\.local\bin`, which is on the already-running OpenCode CLI's PATH, so no restart was needed. Symlinking required admin and `.cmd` shims don't work with Node `spawn`, so copying the two MSYS files was the clean, reversible option.
- **Verified:** Node `spawnSync("sh", ["-c", guard])` exits 0, `command -v entire` resolves, and `entire session list` now shows an active session (`ses_edbbdf…`) created by a real `turn-start` hook.
- **Checkpoint:** this log entry is committed during the active session to confirm commit-linked capture; checkpoint inspected with `entire checkpoint explain`.
- Self-imposed rule carried forward: if capture ever stops, stop and fix — a commit without linked session context is not evidence of capture.