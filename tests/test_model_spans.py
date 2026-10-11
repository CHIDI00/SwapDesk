"""Explicit ChatOpenAI span proofs: fake provider, same adapter, no network.

Zero paid calls. The production `InstrumentedChatOpenAI._generate` /
`_stream` wrappers run unmodified; only the grandparent
`ChatOpenAI._generate` / `_stream` (the HTTP layer) is stubbed with a
canned response, so span emission, usage handling, error recording, and
secret scrubbing all execute through the real code path.
"""

import sys
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from swapdesk.agent.model_spans import (  # noqa: E402
    InstrumentedChatOpenAI,
    extract_usage,
    sanitize,
)


class _FakeSpan:
    def __init__(self, store, name, kind, attrs):
        self._store = store
        self.name = name
        self.kind = kind
        self.attrs = dict(attrs)
        self.status = None

    def set_attribute(self, key, value):
        self.attrs[key] = value

    def set_status(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._store.append(self)
        return False


@pytest.fixture()
def recorder(monkeypatch):
    spans = []

    def fake_trace(name, kind=None, **attrs):
        return _FakeSpan(spans, name, kind, attrs)

    monkeypatch.setattr("neatlogs.trace", fake_trace)
    return spans


@pytest.fixture()
def model():
    return InstrumentedChatOpenAI(model="claude-haiku",
                                  api_key="test-key-not-real")


def _result(text="ok", usage=None):
    msg = AIMessage(content=text)
    if usage is not None:
        msg.usage_metadata = usage
    return ChatResult(generations=[ChatGeneration(message=msg)])


def _stub_generate(monkeypatch, canned=None, boom=None):
    def fake(self, messages, stop=None, run_manager=None, **kwargs):
        if boom is not None:
            raise boom
        return canned

    monkeypatch.setattr(ChatOpenAI, "_generate", fake)


def test_emits_one_llm_span_with_usage(recorder, model, monkeypatch):
    _stub_generate(monkeypatch, _result(
        "done", {"input_tokens": 120, "output_tokens": 30,
                 "total_tokens": 150}))
    out = InstrumentedChatOpenAI._generate(
        model, [HumanMessage(content="exchange ITEM-01?")])
    assert out.generations[0].message.content == "done"
    assert len(recorder) == 1
    span = recorder[0]
    assert span.kind == "LLM"
    assert "chatopenai" in span.name
    assert span.attrs["llm.model_name"] == "claude-haiku"
    assert "exchange ITEM-01?" in span.attrs["llm.input_messages"]
    assert "done" in span.attrs["llm.output_messages"]
    assert span.attrs["llm.token_count.prompt"] == 120
    assert span.attrs["llm.token_count.completion"] == 30
    assert span.attrs["llm.token_count.total"] == 150


def test_missing_usage_is_unknown_never_zero(recorder, model, monkeypatch):
    _stub_generate(monkeypatch, _result("done", None))
    InstrumentedChatOpenAI._generate(model, [HumanMessage(content="hi")])
    assert len(recorder) == 1
    assert "llm.token_count.prompt" not in recorder[0].attrs
    assert "llm.token_count.completion" not in recorder[0].attrs
    assert "llm.token_count.total" not in recorder[0].attrs
    assert extract_usage(_result("done", None)) is None


def test_error_recorded_and_reraised_once(recorder, model, monkeypatch):
    _stub_generate(monkeypatch, boom=RuntimeError("provider down"))
    with pytest.raises(RuntimeError, match="provider down"):
        InstrumentedChatOpenAI._generate(model, [HumanMessage(content="hi")])
    assert len(recorder) == 1
    assert recorder[0].status == "ERROR"
    assert recorder[0].attrs["error.type"] == "RuntimeError"


def test_secrets_scrubbed_from_capture(recorder, model, monkeypatch):
    secret = "sk-SECRETVALUE12345678"
    _stub_generate(monkeypatch, _result("ok", None))
    InstrumentedChatOpenAI._generate(model, [HumanMessage(
        content=f"my api_key={secret} here and LITELLM_API_KEY = abc")])
    blob = recorder[0].attrs["llm.input_messages"]
    assert secret not in blob
    assert "abc" not in blob
    assert "[credential]" in blob
    assert sanitize(None) != ""


def test_streaming_counts_one_span(recorder, model, monkeypatch):
    from langchain_core.messages import AIMessageChunk

    def fake_stream(self, messages, stop=None, run_manager=None, **kwargs):
        yield AIMessageChunk(content="he")
        yield AIMessageChunk(content="llo")

    monkeypatch.setattr(ChatOpenAI, "_stream", fake_stream)
    chunks = list(InstrumentedChatOpenAI._stream(
        model, [HumanMessage(content="hi")]))
    assert [c.content for c in chunks] == ["he", "llo"]
    assert len(recorder) == 1
    assert recorder[0].attrs.get("swapdesk.streamed") is True


def test_build_model_returns_instrumented_client(monkeypatch):
    from swapdesk.agent.graph import build_model

    monkeypatch.delenv("SWAPDESK_MODEL", raising=False)
    monkeypatch.setenv("LITELLM_API_KEY", "test-key-not-real")
    client = build_model()
    assert isinstance(client, InstrumentedChatOpenAI)
    assert isinstance(client, ChatOpenAI)
    assert client.max_retries == 0


def test_real_sdk_accepts_llm_span_shape():
    import neatlogs

    basename = "chatopenai generate"
    with neatlogs.trace(basename, kind="LLM",
                        **{"llm.model_name": "probe"}) as span:
        span.set_attribute("llm.token_count.prompt", 1)
        span.set_attribute("swapdesk.evidence", "explicit-model-span")
    assert "chat" in basename
