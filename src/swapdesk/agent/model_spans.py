"""Explicit model spans for the LiteLLM/ChatOpenAI provider path.

Locked-SDK support audit (neatlogs 1.4.26):
- `neatlogs.wrap()` documents raw OpenAI/AsyncOpenAI clients, not
  LangChain's `ChatOpenAI`. Chat-model capture rides on OpenInference
  LangChain instrumentation, which recorded zero LLM spans for a
  completed proxy-path run (trace `608bd91b...`: llm_calls 0).
- Supported explicit API: `neatlogs.trace(name, kind=..., **attributes)`
  plus `span.set_attribute` / `set_status` on the yielded span.

This module therefore emits exactly one explicit LLM span per model
generation on the ChatOpenAI path, using OpenInference attribute names
so the backend counts it (`openinference.span.kind = "LLM"`). Each
generation is counted once: one span per `_generate` / `_agenerate` /
`_stream` / `_astream` call. Token usage is recorded only when the
provider returns it; absent usage is omitted (unknown), never zero.
`requests_spent` (queue record) stays a separate client-side count.

Secrets: message content is synthetic order data, but anything shaped
like a credential is scrubbed before capture. Error paths record the
error type only, then re-raise so budget/queue semantics are unchanged.
"""

from __future__ import annotations

import json
import re
import time

import neatlogs
from langchain_openai import ChatOpenAI

_MAX_CHARS = 4000

_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|api[_-]?secret|bearer|authorization)\b"
               r"\s*[:=]\s*\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bLITELLM_API_KEY\b\s*=\s*\S+"),
    re.compile(r"\bGEMINI_API_KEY\b\s*=\s*\S+"),
)


def sanitize(text: object) -> str:
    """Render and scrub text for span capture. Never raises."""
    try:
        rendered = text if isinstance(text, str) else json.dumps(
            text, sort_keys=True, default=str)
    except Exception:
        return "<unserializable>"
    for pattern in _SECRET_PATTERNS:
        rendered = pattern.sub("[credential]", rendered)
    if len(rendered) > _MAX_CHARS:
        rendered = rendered[:_MAX_CHARS] + "…[truncated]"
    return rendered


def _message_dicts(messages) -> list:
    out = []
    for message in messages or []:
        try:
            kind = type(message).__name__
            content = getattr(message, "content", "")
            row = {"type": kind, "content": sanitize(content)}
            name = getattr(message, "name", None)
            if name:
                row["name"] = sanitize(name)
            out.append(row)
        except Exception:
            out.append({"type": "?", "content": "<unserializable>"})
    return out


def extract_usage(result) -> dict | None:
    """Provider-returned token usage, or None when absent (unknown)."""
    try:
        generations = getattr(result, "generations", None) or []
        message = generations[0].message if generations else None
        meta = getattr(message, "usage_metadata", None) if message else None
        if isinstance(meta, dict):
            usage = {}
            if isinstance(meta.get("input_tokens"), int):
                usage["prompt"] = meta["input_tokens"]
            if isinstance(meta.get("output_tokens"), int):
                usage["completion"] = meta["output_tokens"]
            if isinstance(meta.get("total_tokens"), int):
                usage["total"] = meta["total_tokens"]
            if usage:
                return usage
        llm_output = getattr(result, "llm_output", None)
        if isinstance(llm_output, dict):
            raw = llm_output.get("token_usage") or {}
            usage = {}
            for source, dest in (("prompt_tokens", "prompt"),
                                 ("completion_tokens", "completion"),
                                 ("total_tokens", "total")):
                if isinstance(raw.get(source), int):
                    usage[dest] = raw[source]
            if usage:
                return usage
    except Exception:
        return None
    return None


def _output_texts(result) -> str:
    try:
        return sanitize([
            getattr(gen.message, "content", "")
            for gen in (getattr(result, "generations", None) or [])])
    except Exception:
        return "<unserializable>"


class InstrumentedChatOpenAI(ChatOpenAI):
    """ChatOpenAI with one explicit LLM span per generation.

    Production behavior is inherited untouched; only observability is
    added. Used for the LiteLLM-proxy branch of `build_model`.
    """

    def _model_id(self) -> str:
        for attr in ("model_name", "model"):
            try:
                value = getattr(self, attr, None)
                if value:
                    return str(value)
            except Exception:
                continue
        return "unknown"

    def _llm_span(self, messages):
        return neatlogs.trace(
            "chatopenai generate", kind="LLM",
            **{"llm.model_name": self._model_id(),
               "llm.input_messages": sanitize(_message_dicts(messages)),
               "swapdesk.provider": "litellm-proxy",
               "swapdesk.evidence": "explicit-model-span"})

    def _record_usage(self, span, result) -> None:
        usage = extract_usage(result)
        if not usage:
            return  # Unknown, never zero.
        if "prompt" in usage:
            span.set_attribute("llm.token_count.prompt", usage["prompt"])
        if "completion" in usage:
            span.set_attribute("llm.token_count.completion",
                               usage["completion"])
        if "total" in usage:
            span.set_attribute("llm.token_count.total", usage["total"])

    def _record_error(self, span, exc: BaseException) -> None:
        try:
            span.set_attribute("error.type", type(exc).__name__)
            span.set_status("ERROR")
        except Exception:
            pass

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        started = time.monotonic()
        with self._llm_span(messages) as span:
            try:
                result = super()._generate(
                    messages, stop=stop, run_manager=run_manager, **kwargs)
            except Exception as exc:
                self._record_error(span, exc)
                raise
            span.set_attribute("llm.output_messages",
                               _output_texts(result))
            self._record_usage(span, result)
            span.set_attribute("swapdesk.latency_ms",
                               int((time.monotonic() - started) * 1000))
            return result

    async def _agenerate(self, messages, stop=None, run_manager=None,
                         **kwargs):
        started = time.monotonic()
        with self._llm_span(messages) as span:
            try:
                result = await super()._agenerate(
                    messages, stop=stop, run_manager=run_manager, **kwargs)
            except Exception as exc:
                self._record_error(span, exc)
                raise
            span.set_attribute("llm.output_messages",
                               _output_texts(result))
            self._record_usage(span, result)
            span.set_attribute("swapdesk.latency_ms",
                               int((time.monotonic() - started) * 1000))
            return result

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        started = time.monotonic()
        with self._llm_span(messages) as span:
            try:
                span.set_attribute("swapdesk.streamed", True)
                yield from super()._stream(
                    messages, stop=stop, run_manager=run_manager, **kwargs)
            except Exception as exc:
                self._record_error(span, exc)
                raise
            finally:
                span.set_attribute("swapdesk.latency_ms",
                                   int((time.monotonic() - started) * 1000))

    async def _astream(self, messages, stop=None, run_manager=None,
                       **kwargs):
        started = time.monotonic()
        with self._llm_span(messages) as span:
            try:
                span.set_attribute("swapdesk.streamed", True)
                async for chunk in super()._astream(
                        messages, stop=stop, run_manager=run_manager,
                        **kwargs):
                    yield chunk
            except Exception as exc:
                self._record_error(span, exc)
                raise
            finally:
                span.set_attribute("swapdesk.latency_ms",
                                   int((time.monotonic() - started) * 1000))
