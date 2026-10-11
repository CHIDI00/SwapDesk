"""Provider-request budget for worker runs. One concern only.

Counts actual model generations (sync and async, streaming included) per
run and refuses before the next request once exhausted. This enforces a
real provider-request limit; graph recursion limits alone do not, since
a loop can spin on tools without calling the model.

Pattern follows StudioMiddleware/capped.BudgetedChatModel: refusals and
failed attempts count, errors expose only a type, never credentials.
"""

from __future__ import annotations

from threading import Lock

from langchain.agents.middleware import AgentMiddleware

from .capped import BudgetExceeded


class RequestBudget(AgentMiddleware):
    """Refuse model calls beyond max_requests for one run."""

    def __init__(self, max_requests: int):
        if type(max_requests) is not int or max_requests < 0:
            raise ValueError("max_requests must be a nonnegative integer")
        self._max = max_requests
        self._spent = 0
        self._lock = Lock()

    @property
    def spent(self) -> int:
        return self._spent

    def _claim(self) -> None:
        with self._lock:
            if self._spent >= self._max:
                raise BudgetExceeded(
                    f"model budget exhausted "
                    f"({self._spent}/{self._max} attempts)")
            self._spent += 1

    def wrap_model_call(self, request, handler):
        # Raise (never a state update): the generic agent state has no
        # error channel, so a refusal must fail loudly and let the worker
        # record a failed run instead of an invented business outcome.
        self._claim()
        try:
            return handler(request)
        except BudgetExceeded:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"agent model failed ({type(exc).__name__}); "
                "inspect local diagnostics") from None

    async def awrap_model_call(self, request, handler):
        self._claim()
        try:
            return await handler(request)
        except BudgetExceeded:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"agent model failed ({type(exc).__name__}); "
                "inspect local diagnostics") from None
