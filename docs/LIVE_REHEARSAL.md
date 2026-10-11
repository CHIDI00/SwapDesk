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
- **Enforced hard cap per case: `SWAPDESK_AGENT_BUDGET=12` provider
  requests**, enforced client-side by RequestBudget (the 13th request
  raises before any call). Across three cases: at most 36 provider
  requests total, plus at most one non-cancellable in-flight request
  per run at a timeout instant. Per-run consumption is persisted as
  `requests_spent` on the run record and exposed on status reads —
  ground truth independent of telemetry capture.
- SDK retries forced to a single attempt (`max_retries=0` on both
  provider paths, attempts=1 on the Gemini wrapper).
- Wall-clock bound per run: `SWAPDESK_RUN_TIMEOUT_S=300`; timeouts record
  failure and queue no retry.
- No automatic retries or reruns anywhere in the path.

## Cost estimate (NOT a maximum — token limits are NOT enforced)

No component caps tokens. The only enforced limits are the request
count above and the wall-clock timeout. The $ figure below is an
**estimate**, not a maximum:

Worst case per run: 12 requests × ~10k input tokens ≈ 120k input +
~6k output. At public Claude Haiku 4.5 rates ($1/MTok input,
$5/MTok output): ≈ $0.15 per run, ≈ **$0.45 estimated total** (realistic
usage is ~5–10× lower). Three separate facts, not one guarantee:

1. **Client request cap** (12/run, enforced): bounds generations, not
   tokens or dollars.
2. **Proxy billing and retry behavior** (not controlled here): actual
   charges follow the hackathon LiteLLM proxy (credits); any
   proxy-side retries are invisible to the client budget.
3. **Token usage**: measured after the fact from traces, never capped
   beforehand.

## neatlogs evidence requirements (per case, mandatory)

Each rehearsal case must produce, before it counts as evidence:

- A completed neatlogs workflow trace with matching `case_id`, `run_id`,
  and tested commit recorded alongside it.
- Available model/tool inputs and outputs from the trace (concise
  observed events only — no private chain-of-thought, no secrets).
- Outcome plus verification evidence (saved DB state: exchanges,
  returns, labels, stock; `requests_spent`; latency from run
  timestamps; cost with its pricing basis).
- For recovery (case C): the injected timeout record, the
  operation-status lookup, the original operation key, and proof of no
  duplicate effects (exactly one of each fulfillment row).

Retrieval procedure after each case (read-only; a repo-local script can
drive the `search_traces` / `get_trace_context` MCP tools):

1. Flush (the worker flushes every path; `--once` never exits unflushed).
2. `search_traces` for the case id; `get_trace_context` on the hit.
3. An export attempt, a local trace id, or a flush is **not** proof —
   only a retrieved trace counts.

If retrieval fails: preserve all local evidence (status/timeline JSON,
DB file), record the trace as **missing**, and **stop**. Do not rerun
the model to obtain a better trace; read-only retrieval may be retried
separately.

Known capture gap (observed 2026-10-11): a completed proxy-path run can
record `llm_calls: 0` / zero tokens in neatlogs even though the agent
executed. Per-case `requests_spent` (client-counted, persisted) is the
primary usage record; neatlogs token/cost fields are secondary and may
be absent — absent fields are reported as missing, never filled in.

Update 2026-10-11 (telemetry gap closed): the LiteLLM-proxy client now
emits one explicit LLM span per generation (`src/swapdesk/agent/
model_spans.py`, wired in `build_model`), recording model, sanitized
input/output, latency, returned usage when present (omitted when
absent), and error type on failure. `neatlogs.wrap()` was verified to
match only concrete client classes and cannot cover this subclass, so
`maybe_wrap_provider` returns it unwrapped with explicit spans as the
single counting point. Offline proofs: `tests/test_model_spans.py`
(fake provider through the real adapter, no network).

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
