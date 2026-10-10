"""Scripted model doubles for offline wiring verification.

These replay canned tool calls against the REAL backend with zero model
requests. They prove the wiring (tools, keys, state, replies), never
Gemini's decisions. Anything claiming model behavior from these runs
is a false-resolution claim.
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr

WIRING_LABEL = "offline wiring verification (not Gemini behavior)"


class ScriptedChatModel(BaseChatModel):
    """Test double: replays canned messages, binds tools as passthrough."""

    _msgs: object = PrivateAttr()

    def __init__(self, messages):
        super().__init__()
        self._msgs = iter(messages)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        try:
            msg = next(self._msgs)
        except StopIteration:
            msg = AIMessage(content="out of script; stopping.")
        return ChatResult(generations=[ChatGeneration(message=msg)])

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self


def call(name: str, args: dict, cid: str = "c1") -> AIMessage:
    """One canned tool call."""
    return AIMessage(content="", tool_calls=[
        {"name": name, "args": args, "id": cid, "type": "tool_call"}])


# Demo scenarios use fresh DEMO-* cases only; benchmark cases (and their
# expected answers) are never loaded here. Holdouts stay out by design.
SCENARIOS = {
    "arrange": {"order_id": "ORD-1001", "order_item_id": "ITEM-01",
                "size": "42", "sku": "AIRFLOW-RUNNER",
                "message": "Please exchange ITEM-01 on order ORD-1001 "
                           "for size 42."},
    "deny": {"order_id": "ORD-1001", "order_item_id": "ITEM-02",
             "size": "40", "sku": "COURT-CLASSIC",
             "message": "Please exchange ITEM-02 on order ORD-1001 "
                        "for size 40."},
    "recover": {"order_id": "ORD-1003", "order_item_id": "ITEM-04",
                "size": "44", "sku": "COURT-CLASSIC",
                "message": "Please exchange ITEM-04 on order ORD-1003 "
                           "for size 44."},
}


def script_for(scenario: str, case_id: str, run_id: str) -> list:
    """Canned tool-call script for a scenario. Ids are deterministic on a
    fresh database, which isolated cases always provide."""
    if scenario == "arrange":
        cfg = SCENARIOS["arrange"]
        eid = "EXC-ITEM-01-1"
        return [
            call("get_order", {"order_id": cfg["order_id"]}),
            call("find_exchange_stock",
                 {"sku": cfg["sku"], "size": cfg["size"]}),
            call("reserve_replacement",
                 {"order_id": cfg["order_id"],
                  "order_item_id": cfg["order_item_id"], "size": cfg["size"]}),
            call("create_return", {"exchange_id": eid}),
            call("create_label", {"exchange_id": eid}),
            call("finalize_arranged", {"exchange_id": eid}),
            AIMessage(content="arranged"),
        ]
    if scenario == "deny":
        cfg = SCENARIOS["deny"]
        return [
            call("get_order", {"order_id": cfg["order_id"]}),
            call("reserve_replacement",
                 {"order_id": cfg["order_id"],
                  "order_item_id": cfg["order_item_id"], "size": cfg["size"]}),
            call("record_denial", {"reason": "sold as final sale"}),
            AIMessage(content="denied"),
        ]
    if scenario == "recover":
        cfg = SCENARIOS["recover"]
        eid = "EXC-ITEM-04-1"
        op_key = f"{case_id}:{run_id}:reserve"
        return [
            call("reserve_replacement",
                 {"order_id": cfg["order_id"],
                  "order_item_id": cfg["order_item_id"], "size": cfg["size"]},
                 cid="r-crash"),
            call("get_operation_status", {"op_key": op_key}, cid="r-status"),
            call("reserve_replacement",
                 {"order_id": cfg["order_id"],
                  "order_item_id": cfg["order_item_id"], "size": cfg["size"]},
                 cid="r-retry"),
            call("create_return", {"exchange_id": eid}, cid="r-ret"),
            call("create_label", {"exchange_id": eid}, cid="r-lab"),
            call("finalize_arranged", {"exchange_id": eid}, cid="r-fin"),
            AIMessage(content="recovered and arranged"),
        ]
    raise ValueError(f"unknown scenario {scenario!r}; "
                     f"choose one of {sorted(SCENARIOS)}")
