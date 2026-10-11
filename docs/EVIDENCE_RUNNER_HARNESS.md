# Evidence: trace-assisted runner/harness fix (denial evidence path)

Scope: runner/harness correctness. NOT improved model reasoning.

## 1. Original diagnostic trace

- Trace `0b32a1f5afd7a6bfa1ea6b7d6baf6091` (`swapdesk:D1-final-sale`, success,
  5 spans, 0 LLM calls). Retrieve read-only via MCP `get_trace_context`
  with that trace ID on the bound project. No dashboard URL scheme was
  observed, so trace IDs (not links) are the verifiable reference.
- Observed facts: the `record_denial` span input carried the full policy
  reason and returned `{ok:true, state:denied}`; the `log` span recorded
  `case D1-final-sale -> denial`; the root workflow output was only
  `Ok: true`.
- Interpretation (separate from facts): the trace proves the reason was
  persisted at tool level. It cannot show the runner's Python return
  value. The omission was proven by source inspection (`run_agent`
  dropped `decided["data"]`) plus the local checker failure
  `expected message containing 'final sale', got ''` (baseline D1,
  claude-haiku, ~$0.0104/run).

## 2. Controlled comparison (2 live executions, 0 reruns)

- Case `D1-final-sale` (ITEM-02 final sale, ORD-1001), `RUN-1`, identical
  composed request, fresh identical fixtures (business rows byte-identical;
  fixture digests differ only by DB creation timestamps), model
  `claude-haiku` via LiteLLM proxy, default bounds, unchanged `check_run`,
  current safety behavior.
- Base `1655724`. BEFORE = base with exactly two reversals: `graph.py`
  minus `"data": decided["data"],`; `_run_log` restricted to
  `== "denied"` / `== "escalated"`. AFTER = pristine base. The variant
  lived in temp worktrees only; `main` was never modified for the runs.
- Caps: max 8 provider requests (generate-level wrapper; tool-call/graph
  limits were not used as the cap), 180 s timeout per run, $0.10
  client-side soft gate, 0 retries. SDK retries off (`max_retries=0`
  asserted in-run); proxy-side retries are outside client control.

## 3. Results

| | BEFORE (controlled reproduction) | AFTER (fixed code) |
|---|---|---|
| Trace | `79a02458552943d874ebdf8d48e6ef0d` | `8d4b7cc8affd12b46873a56318f8dcd8` |
| Runner outcome / `has_data` | denial / false | denial / true |
| Harness `log.reason` | `''` (lost) | full policy reason (preserved) |
| Checker | FAIL `expected message containing 'final sale', got ''` | PASS, no failures |
| Persisted case state | `denied` + full reason note | `denied` + full reason note |
| Side effects | 0 exchanges/returns/labels/ops; stock unchanged | same |
| Provider requests / latency / est. cost | 3 / 8.3 s / $0.008627 | 3 / 7.6 s / $0.008478 |

Captured reason text (synthetic fixture data; wording varies by model
nondeterminism, checker needle `'final sale'` matched the AFTER wording):
- BEFORE persisted note: "ITEM-02 (COURT-CLASSIC, size 40) on order
  ORD-1001 is marked as final sale and the shop's return policy excludes
  final-sale items from exchange eligibility."
- AFTER runner data: "ITEM-02 on ORD-1001 is marked final sale and
  excluded by the shop's return policy."

## 4. Cost basis and control limits

- Estimates use Anthropic Haiku list rates ($1.00/$5.00 per M in/out);
  the proxy bills a shared pool at its own rates, so actuals may differ.
  Total measured: $0.017105 (~$0.02).
- $0.10 is a client-side soft gate over a 2-run ledger, not a guaranteed
  ceiling. A cap breach would have ended the run as a recorded failure;
  never triggered (3 requests each, cap 8).

## 5. Fix identity

- Commit `90c89d8` (`graph.py` +1 line, `baseline.py` harness mapping,
  `tests/test_evidence_path.py`). Checkpoint `01M4KJS2K88G9T2AWH11WVZG44`
  references `90c89d8`. Deterministic suite: 106 passed, 1 skipped;
  evidence-path file: 3 passed. Checker never weakened.

## 6. Explicitly pending (not claimed)

- No full 42-run re-baseline; V1 (16/42) / V2 (20/42) scores provisional.
- Recovery/crash paths not covered by this evidence; model decision
  errors remain (e.g. v2 A13/C3); no video, X post, or submission
  artifacts from this work.
