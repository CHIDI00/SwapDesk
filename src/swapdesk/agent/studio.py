"""LangGraph Studio entrypoints. Two clearly labeled modes.

- offline_graph (default): scripted model replays tool calls against the
  real backend. Zero model requests. Wiring verification only, never
  proof of Gemini's decisions.
- live_graph (opt-in): budget-capped Gemini. Needs an explicit per-run
  budget plus SWAPDESK_MODEL and GEMINI_API_KEY; anything missing fails
  loudly before any model call. No live calls happen unless a budgeted
  smoke test is explicitly invoked.

Persistence note: the served graphs are compiled WITHOUT a checkpointer
because the LangGraph platform provides thread persistence automatically
(a custom SqliteSaver is rejected at load). Resume still works: threads
persist server-side, while case isolation, operation keys, and business
state live in the case database. Tests pass an explicit file saver to
the same builders.
"""

from __future__ import annotations

from swapdesk.agent.studio_flow import build_live_graph, build_offline_graph

offline_graph = build_offline_graph()
live_graph = build_live_graph()
