# Live rehearsal plan — queued agent endpoint, three cases

Status: PREPARED, not executed. No paid calls made under this plan yet.
Execute only on explicit approval, exactly as written. If any case
fails, preserve its evidence and stop — no automatic retries or reruns.

## Cases (isolated synthetic fixture databases, no cross-contamination)

| Case | DB file | Intake `POST /v1/agent/tickets` | Fault injection | Expected verified result |
|---|---|---|---|---|
| A eligible exchange | `a.db` | message + ORD-1001 / ITEM-01 / size 42, `case_id` LIVE-A | none | arranged: 1 exchange, 1 return, 1 label, stock consumed once, reply carries `TRK-MOCK-` |
| B final sale | `b.db` | message + ORD-1001 / ITEM-02 / size 40, `case_id` LIVE-B | none | denial: persisted reason mentioning final sale, zero exchange/return/label rows, empty timeline |
| C lost label response | `c.db` | message + ORD-1001 / ITEM-01 / size 42, `case_id` LIVE-C | `label`/`timeout` ×1 on `LIVE-C:RUN-1:label`, enabled only for this round | arranged via same-key recovery: exactly 1 label row, 1 committed label op, no duplicate reservation/return/label |

All under `$env:TEMP\swapdesk-rehearsal` (outside the repo):
`a.db`, `b.db`, `c.db`, plus `<db>.agent-checkpoints.sqlite` siblings and
`out\` for saved status/timeline JSON. Never run the worker unattended:
it polls forever by design, so rehearsal uses `worker --once` per round
under supervision, or a background job that is stopped immediately after.

## Exact commands per round (PowerShell, Windows)

Setup (once):

```powershell
$R = "$env:TEMP\swapdesk-rehearsal"
New-Item -ItemType Directory -Force -Path "$R\out" | Out-Null
$env:SWAPDESK_AGENT_BUDGET = "12"
$env:SWAPDESK_RUN_TIMEOUT_S = "300"
```

Round A (repeat with `b.db`/case B payload; C adds the fault step):

```powershell
$env:SWAPDESK_DB = "$R\a.db"
$api = Start-Job -ScriptBlock {
  param($w, $d)
  $env:SWAPDESK_DB = $d; $env:SWAPDESK_TELEMETRY_ENV = "0"
  Set-Location $w; uv run uvicorn swapdesk.api:app --port 8000 2>&1
} -ArgumentList (Get-Location).Path, $env:SWAPDESK_DB
Start-Sleep -Seconds 12
Invoke-RestMethod http://127.0.0.1:8000/v1/agent/tickets -Method Post `
  -ContentType "application/json" `
  -Body '{"message":"Please exchange ITEM-01 on order ORD-1001 for size 42","order_id":"ORD-1001","order_item_id":"ITEM-01","size":"42","case_id":"LIVE-A"}'
uv run python -m swapdesk.worker --once
Invoke-RestMethod http://127.0.0.1:8000/v1/agent/cases/LIVE-A |
  ConvertTo-Json -Depth 8 | Out-File "$R\out\a-status.json"
Invoke-RestMethod http://127.0.0.1:8000/v1/agent/cases/LIVE-A/timeline |
  ConvertTo-Json -Depth 8 | Out-File "$R\out\a-timeline.json"
Stop-Job $api; Remove-Job -Force $api
```

Case C fault step only (after intake, before `--once`, same round):

```powershell
$env:SWAPDESK_ENABLE_DEMO_FAULTS = "1"
Invoke-RestMethod http://127.0.0.1:8000/v1/demo/faults -Method Post `
  -Content-Type "application/json" `
  -Body '{"case_id":"LIVE-C","run_id":"RUN-1","step":"label","point":"timeout"}'
Remove-Item Env:\SWAPDESK_ENABLE_DEMO_FAULTS
```

## Spend controls in force for all three rounds

- Provider: hackathon LiteLLM proxy, model `claude-haiku` (from `.env`;
  values never printed, `.env` never committed).
- Hard cap per case: `SWAPDESK_AGENT_BUDGET=12` provider requests,
  enforced client-side by RequestBudget (13th request raises before any
  call). Across three cases: at most 36 provider requests total.
- SDK retries forced to a single attempt (`max_retries=0` on both
  provider paths, attempts=1 on the Gemini wrapper).
- Wall-clock bound per run: `SWAPDESK_RUN_TIMEOUT_S=300`; timeouts record
  failure and queue no retry.
- No automatic retries or reruns anywhere in the path.

## Cost ceiling (estimate, public rates)

Worst case per run: 12 requests × ~10k input tokens ≈ 120k input +
~6k output. At public Claude Haiku 4.5 rates ($1/MTok input,
$5/MTok output): ≈ $0.15 per run, ≈ **$0.45 for all three** — stated as
a ceiling, not a prediction (realistic usage is ~5–10× lower). Actual
billing goes through the hackathon LiteLLM proxy (credits), which may
differ; real token counts will be read back from the run traces.

## Spend-control limitations (known, accepted)

- An in-flight request at the timeout instant cannot be cancelled and
  is still billed (at most one extra request per run).
- Proxy-side retries, if any, are invisible to the client budget; only
  client-issued generations are counted.
- Token figures above are bounds until measured; actuals come from
  traces after execution.

## Where results and traces go

- Raw: `$env:TEMP\swapdesk-rehearsal\out\` (`{a,b,c}-status.json`,
  `{a,b,c}-timeline.json`) plus the three isolated DBs — all outside
  tracked files.
- neatlogs: local capture always; exported trace links (if export is
  configured) collected per run.
- Committed after execution: `docs/EVIDENCE_LIVE_REHEARSAL.md` (per-case
  outcome, evidence, trace links or explicit "missing") plus a
  `hackathon.md` entry. Failing cases are recorded as-is; no rerun.
