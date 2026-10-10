"""Provider factory proofs: env-driven selection, zero API spend."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from swapdesk import telemetry  # noqa: E402
from swapdesk.agent.graph import (  # noqa: E402
    ConfigurationError,
    build_model,
)


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    monkeypatch.setenv("SWAPDESK_TELEMETRY_ENV", "0")
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("SWAPDESK_MODEL", raising=False)
    yield


def test_litellm_selected_with_defaults(monkeypatch):
    from langchain_openai import ChatOpenAI

    monkeypatch.setenv("LITELLM_API_KEY", "test-key-not-real")
    client = build_model()
    assert isinstance(client, ChatOpenAI)
    assert client.model_name == "claude-haiku"
    assert str(client.openai_api_base).rstrip("/") == \
        "https://litellm.vision.aivar.app/v1"
    assert client.max_retries == 0


def test_litellm_honors_model_and_base_overrides(monkeypatch):
    from langchain_openai import ChatOpenAI

    monkeypatch.setenv("LITELLM_API_KEY", "test-key-not-real")
    monkeypatch.setenv("SWAPDESK_MODEL", "nova-micro")
    monkeypatch.setenv("LITELLM_BASE_URL", "https://proxy.example/v1")
    client = build_model()
    assert isinstance(client, ChatOpenAI)
    assert client.model_name == "nova-micro"
    assert str(client.openai_api_base).rstrip("/") == \
        "https://proxy.example/v1"


def test_gemini_fallback_without_litellm(monkeypatch):
    from langchain_google_genai import ChatGoogleGenerativeAI

    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    client = build_model()
    assert isinstance(client, ChatGoogleGenerativeAI)
    assert client.model == "gemini-3.8-flash"
    assert client.max_retries == 0


def test_no_provider_is_a_clear_error():
    with pytest.raises(ConfigurationError):
        build_model()


def test_wrap_covers_openai_client(monkeypatch):
    from langchain_openai import ChatOpenAI

    monkeypatch.setenv("LITELLM_API_KEY", "test-key-not-real")
    wrapped = telemetry.maybe_wrap_provider(build_model())
    assert isinstance(wrapped, ChatOpenAI)
    assert telemetry.maybe_wrap_provider(object()) is not None
