"""Hard model-request budget for live runs.

The graph recursion limit bounds loop STEPS, not API requests: retries,
re-reads, and multi-call turns all slip past it. This wrapper counts
every generation request (retries included, since they re-enter
_generate) and refuses past the cap. The refusal is loud by design:
a capped run fails explicitly, never as a fake success.
"""

from __future__ import annotations

from pydantic import PrivateAttr


class BudgetExceeded(Exception):
    """The live model-request budget is spent. No further calls made."""


class BudgetedGemini:
    """Factory namespace; the capped model class is BudgetedChatModel."""


try:
    from langchain_google_genai import ChatGoogleGenerativeAI as _GeminiBase
except Exception:  # pragma: no cover - import-time fallback
    _GeminiBase = None  # type: ignore


if _GeminiBase is not None:
    class BudgetedChatModel(_GeminiBase):  # type: ignore[valid-type]
        """ChatGoogleGenerativeAI with a hard request budget."""

        _budget: int = PrivateAttr(default=0)
        _spent: int = PrivateAttr(default=0)

        def set_budget(self, n: int) -> "BudgetedChatModel":
            self._budget = int(n)
            return self

        @property
        def spent(self) -> int:
            return self._spent

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            if self._spent >= self._budget:
                raise BudgetExceeded(
                    f"model budget exhausted ({self._spent}/"
                    f"{self._budget} requests); refusing the call")
            self._spent += 1
            return super()._generate(messages, stop=stop,
                                     run_manager=run_manager, **kwargs)
else:  # pragma: no cover - import-time fallback
    class BudgetedChatModel:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise ImportError("langchain-google-genai is not installed")
