"""neatlogs wiring for SwapDesk. One concern only: telemetry setup.

Safe without credentials: init() without a key captures spans locally
but exports nothing (per the neatlogs SDK contract). Nothing here ever
reads a secret value into a log or transcript; exporting is detected by
key presence alone. Secrets live in `.env` (git-ignored); this module
loads that file into process env at runtime without printing anything.

Call init_telemetry() once per process, flush() after each run.
"""

from __future__ import annotations

import os
from pathlib import Path

import neatlogs

WORKFLOW_NAME = "swapdesk"
BENCHMARK_VERSION = "benchmark-v1"

_configured = False
_exporting = False


def load_dotenv(repo: str | Path | None = None) -> None:
    """Load KEY=VALUE lines from `.env` into process env (no override).

    Tiny on purpose: avoids a dependency for one file. Never prints values.
    Set SWAPDESK_TELEMETRY_ENV=0 to skip (tests stay hermetic).
    """
    if os.environ.get("SWAPDESK_TELEMETRY_ENV") == "0":
        return
    path = Path(repo or Path(__file__).resolve().parent.parent.parent) / ".env"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def init_telemetry(workflow_name: str = WORKFLOW_NAME,
                   capture_logs: bool = True) -> bool:
    """Initialize neatlogs once. Returns True only when exporting."""
    global _configured, _exporting
    if _configured:
        return _exporting
    load_dotenv()
    _exporting = "NEATLOGS_API_KEY" in os.environ
    neatlogs.init(workflow_name=workflow_name, capture_logs=capture_logs)
    _configured = True
    return _exporting


def is_exporting() -> bool:
    """True when a key is present and spans leave this process."""
    return _exporting


def maybe_wrap_gemini(client):
    """Wrap a real Gemini chat client for LLM-span capture; passthrough."""
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except Exception:
        return client
    if isinstance(client, ChatGoogleGenerativeAI):
        return neatlogs.wrap(client, surface="swapdesk-agent")
    return client


def flush() -> None:
    neatlogs.flush()


def shutdown() -> None:
    neatlogs.shutdown()
