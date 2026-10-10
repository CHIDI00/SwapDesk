"""LangGraph Studio entrypoint. Visualization only, not a live run.

The compiled graph below has the exact production wiring (same tools,
same prompts, same bounded loop). The model is a local stand-in because
Studio only needs the graph structure to draw it, and this machine has
no live model route. Invoking it here returns canned model text, never
a real decision. Live runs use run_agent() with a Gemini model.
"""

from __future__ import annotations

from langchain_core.language_models.fake_chat_models import (
    GenericFakeChatModel,
)
from langchain_core.messages import AIMessage

from swapdesk.agent.graph import AgentContext, build_agent

STUDIO_DB_PATH = "studio.db"

_STAND_IN = GenericFakeChatModel(messages=iter([AIMessage(
    content="Studio stand-in: configure SWAPDESK_MODEL plus "
            "GEMINI_API_KEY and run run_agent() for a live case.")]))

graph = build_agent(
    AgentContext(db_path=STUDIO_DB_PATH, case_id="STUDIO",
                 run_id="STUDIO-1",
                 message="Studio visualization stand-in"),
    model=_STAND_IN,
)
