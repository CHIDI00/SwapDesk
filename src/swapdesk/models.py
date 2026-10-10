"""Typed records and shared constants. No I/O here."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

TERMINAL_EXCHANGE_STATUSES = frozenset({"cancelled", "denied"})

OP_RESERVE = "reserve_replacement"


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


@dataclass(frozen=True)
class ReservationResult:
    exchange_id: str
    status: str
    duplicate: bool


def payload_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
