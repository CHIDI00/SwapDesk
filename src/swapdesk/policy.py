"""Eligibility policy. Pure function of the item record and today's date.

The backend enforces this; the agent never decides eligibility itself.
"""

from __future__ import annotations

from datetime import date

from .models import OrderItem

RETURN_WINDOW_DAYS = 30


def check_eligibility(item: OrderItem, today: date) -> tuple[bool, str]:
    """Return (eligible, reason). Reason is empty when eligible."""
    if item.status != "delivered":
        return False, f"item status is {item.status!r}, only delivered items qualify"
    if item.final_sale:
        return False, "item was sold as final sale"
    if not item.delivered_at:
        return False, "item has no delivery date on record"
    delivered = date.fromisoformat(item.delivered_at)
    age = (today - delivered).days
    if age < 0:
        return False, "delivery date is in the future"
    if age > RETURN_WINDOW_DAYS:
        return False, f"delivered {age} days ago, window is {RETURN_WINDOW_DAYS} days"
    return True, ""
