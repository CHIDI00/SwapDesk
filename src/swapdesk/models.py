"""Typed records and shared constants. No I/O here."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

TERMINAL_EXCHANGE_STATUSES = frozenset(
    {"cancelled", "denied", "arranged", "escalated"}
)

OP_RESERVE = "reserve_replacement"
OP_RETURN = "create_return"
OP_LABEL = "create_label"
OP_ARRANGE = "finalize_arranged"
OP_RELEASE = "release_reservation"
OP_CANCEL = "cancel_exchange"
OP_ESCALATE = "escalate_case"

# Legal fulfillment transitions on exchanges.status. Anything not listed
# here raises IllegalTransitionError and writes nothing. Terminal states
# have no outgoing edges.
EXCHANGE_TRANSITIONS: dict[str, frozenset[str]] = {
    "replacement_reserved": frozenset(
        {"return_created", "cleanup_pending", "escalated", "denied",
         "cancelled"}
    ),
    "return_created": frozenset(
        {"label_created", "cleanup_pending", "escalated", "denied",
         "cancelled"}
    ),
    "label_created": frozenset(
        {"arranged", "cleanup_pending", "escalated", "denied", "cancelled"}
    ),
    "cleanup_pending": frozenset({"escalated", "cancelled"}),
    "arranged": frozenset(),
    "escalated": frozenset(),
    "denied": frozenset(),
    "cancelled": frozenset(),
}

# Case-level progress states. Fulfillment ops mirror the exchange status
# here; received / needs_information / denied are recorded via note_case
# and involve no fulfillment writes.
CASE_STATES = frozenset(
    {"received", "needs_information", "denied", "replacement_reserved",
     "return_created", "label_created", "arranged", "cleanup_pending",
     "escalated", "cancelled"}
)


@dataclass(frozen=True)
class Order:
    id: str
    customer_ref: str
    created_at: str


@dataclass(frozen=True)
class OrderItem:
    id: str
    order_id: str
    sku: str
    size: str
    qty: int
    price_cents: int
    status: str
    delivered_at: str | None
    final_sale: bool
    created_at: str


@dataclass(frozen=True)
class StockLevel:
    sku: str
    size: str
    on_hand: int
    held: int

    @property
    def available(self) -> int:
        return self.on_hand - self.held


@dataclass(frozen=True)
class ExchangeRecord:
    id: str
    case_id: str
    order_id: str
    order_item_id: str
    requested_size: str
    authorized_size: str
    qty: int
    status: str
    hold_released: bool = False


@dataclass(frozen=True)
class ReservationResult:
    exchange_id: str
    status: str
    duplicate: bool


@dataclass(frozen=True)
class ReturnResult:
    exchange_id: str
    return_id: str
    status: str
    duplicate: bool


@dataclass(frozen=True)
class LabelResult:
    exchange_id: str
    label_id: str
    tracking_ref: str
    status: str
    duplicate: bool


@dataclass(frozen=True)
class FinalizeResult:
    exchange_id: str
    status: str
    duplicate: bool


@dataclass(frozen=True)
class ReleaseResult:
    exchange_id: str
    status: str
    duplicate: bool
    hold_released: bool


@dataclass(frozen=True)
class EscalationResult:
    exchange_id: str | None
    status: str
    duplicate: bool


@dataclass(frozen=True)
class ExchangeHandoff:
    """Read-only recovery handoff. Inspect, then act with the matching op."""
    exchange_id: str
    case_id: str
    status: str
    return_id: str | None
    label_id: str | None
    tracking_ref: str | None
    hold_active: bool
    pending_cleanup: bool
    consistent: bool
    suggested_next: str


def payload_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
