"""Generate the committed benchmark evidence file."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from eval.harness import run_benchmark  # noqa: E402

cases = json.loads((ROOT / "eval" / "cases_v1.json").read_text())["cases"]
results = run_benchmark(cases)
out = ROOT / "eval" / "results" / "v1.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
print(f"cases={len(cases)} total={results['total']} "
      f"passed={results['passed']} failed={results['failed']} -> {out}")
for run in results["runs"]:
    if not run["passed"]:
        print(f"FAIL {run['case_id']}#{run['repeat']}: {run['failures']}")
