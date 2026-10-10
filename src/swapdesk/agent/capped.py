"""Gemini generation-attempt cap, including streaming and async entrypoints.

SDK retries are forced to one attempt. Each allowed generation can therefore
make at most one model request. Refusals and failed attempts also consume budget.
No keys or client details are exposed by this wrapper.
"""
from __future__ import annotations

from threading import Lock
from pydantic import PrivateAttr
from google.genai.types import HttpOptions, HttpRetryOptions
from langchain_google_genai import ChatGoogleGenerativeAI


class BudgetExceeded(Exception):
    """No more generation attempts are authorized."""


class BudgetedChatModel(ChatGoogleGenerativeAI):
    _budget: int = PrivateAttr(default=0)
    _spent: int = PrivateAttr(default=0)
    _budget_lock: Lock = PrivateAttr(default_factory=Lock)

    def set_budget(self, n: int) -> "BudgetedChatModel":
        if type(n) is not int or n < 0:
            raise ValueError("budget must be a nonnegative integer")
        with self._budget_lock:
            self._budget = n
        return self

    @property
    def spent(self) -> int:
        return self._spent

    def _claim(self):
        with self._budget_lock:
            if self._spent >= self._budget:
                raise BudgetExceeded(
                    f"model budget exhausted ({self._spent}/{self._budget} attempts)")
            self._spent += 1

    def _prepare_request(self, *args, **kwargs):
        # Both model-level and call-level settings must be constrained. The SDK
        # merges per-call HttpOptions after max_retries, so enforce BOTH.
        kwargs["max_retries"] = 1
        supplied = kwargs.get("http_options")
        if isinstance(supplied, HttpOptions):
            supplied = supplied.model_dump(exclude_none=True)
        options = dict(supplied or {})
        options["retry_options"] = HttpRetryOptions(attempts=1)
        kwargs["http_options"] = HttpOptions(**options)
        return super()._prepare_request(*args, **kwargs)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._claim()
        return super()._generate(messages, stop=stop,
                                 run_manager=run_manager, **kwargs)

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        self._claim()
        return await super()._agenerate(messages, stop=stop,
                                       run_manager=run_manager, **kwargs)

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        self._claim()
        yield from super()._stream(messages, stop=stop,
                                   run_manager=run_manager, **kwargs)

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        self._claim()
        async for chunk in super()._astream(messages, stop=stop,
                                           run_manager=run_manager, **kwargs):
            yield chunk
