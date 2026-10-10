"""LangGraph Studio entrypoints. Two clearly labeled modes.

- offline_graph (default): scripted model replays tool calls against the
  real backend. Zero model requests. Wiring verification only, never
  proof of Gemini's decisions.
- live_graph (opt-in): budget-capped Gemini. Needs an explicit per-run
  budget plus SWAPDESK_MODEL and GEMINI_API_KEY; anything missing fails
  loudly before any model call. No live calls happen unless a budgeted
  smoke test is explicitly invoked.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from swapdesk.agent.studio_flow import (
    STUDIO_ROOT,
    build_live_graph,
    build_offline_graph,
)

# Env-aware so tests stay out of the repo tree; the server uses the default.
_threads_db = Path(os.environ.get("SWAPDESK_STUDIO_ROOT", STUDIO_ROOT)) / "studio_threads.db"
_threads_db.parent.mkdir(parents=True, exist_ok=True)
_saver_conn = sqlite3.connect(str(_threads_db), check_same_thread=False)
_saver = SqliteSaver(_saver_conn)

offline_graph = build_offline_graph(checkpointer=_saver)
live_graph = build_live_graph(checkpointer=_saver)
