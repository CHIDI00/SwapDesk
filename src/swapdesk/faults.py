"""Demo-only failure injection for recovery tests.

Test code arms faults by idempotency key; operations consume them at fixed
instrumentation points. Production paths never call inject(). A consumed
fault fires once; inject() again (or pass times=N) for repeated faults.

Points:
  "transient"     - raise before any write; retry with the same key.
  "deplete_stock" - drain the requested pool inside the transaction, then
                    fail the reservation (rolls back; proves check-then-act
                    is atomic).
  "crash"         - raise after commit (worker died; state kept, caller
                    must re-query op status and retry the same key).
  "timeout"       - raise after commit (label response lost).
  "release_fail"  - persist cleanup_pending, then raise (retry same key).
"""

from __future__ import annotations

_counts: dict[tuple[str, str], int] = {}


def inject(op_key: str, point: str, times: int = 1) -> None:
    """Arm a fault for the next `times` consumptions. Test-only."""
    if times < 1:
        raise ValueError("times must be at least 1")
    key = (op_key, point)
    _counts[key] = _counts.get(key, 0) + times


def consume(op_key: str, point: str) -> bool:
    """Consume one armed fault; False when none is armed."""
    key = (op_key, point)
    remaining = _counts.get(key, 0)
    if remaining < 1:
        return False
    if remaining == 1:
        del _counts[key]
    else:
        _counts[key] = remaining - 1
    return True


def clear() -> None:
    """Disarm every fault. Tests call this in teardown."""
    _counts.clear()
