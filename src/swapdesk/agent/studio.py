"""LangGraph Studio entrypoint. Visualization only, not a live run.

The compiled graph below has the exact production wiring (same tools,
same prompts, same bounded loop). The model is a local stand-in because
this machine has no live model route. Invoking it here returns canned
model text and never calls tools, never a real decision. Live runs use
run_agent() with a Gemini model.
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from swapdesk.agent.graph import AgentContext, build_agent

STUDIO_DB_PATH = "studio.db"


class StudioStandIn(BaseChatModel):
    """Canned model so Studio can execute the real graph offline."""

    @property
    def _llm_type(self) -> str:
        return "studio-stand-in"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(
            content="Studio stand-in: configure SWAPDESK_MODEL plus "
                    "GEMINI_API_KEY and run run_agent() for a live case."))])

    def bind_tools(self, tools, **kwargs):
        return self


graph = build_agent(
    AgentContext(db_path=STUDIO_DB_PATH, case_id="STUDIO",
                 run_id="STUDIO-1",
                 message="Studio visualization stand-in"),
    model=StudioStandIn(),
)
