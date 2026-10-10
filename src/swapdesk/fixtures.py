"""Synthetic shop fixtures. Fictional data only; no real customers."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from .db import utcnow


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def load_fixtures(conn: sqlite3.Connection) -> None:
    now = utcnow()
    conn.executemany(
        "INSERT INTO orders (id, customer_ref, created_at) VALUES (?, ?, ?)",
        [
            ("ORD-1001", "SYN-001", now),
            ("ORD-1002", "SYN-002", now),
            ("ORD-1003", "SYN-003", now),
            ("ORD-1004", "SYN-004", now),
            ("ORD-1005", "SYN-005", now),
            ("ORD-1006", "SYN-006", now),
        ],
    )
    conn.executemany(
        """INSERT INTO order_items
           (id, order_id, sku, size, qty, price_cents, status,
            delivered_at, final_sale, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            # Eligible workhorse item.
            ("ITEM-01", "ORD-1001", "AIRFLOW-RUNNER", "42", 1, 12999,
             "delivered", _days_ago(5), 0, now),
            # Final sale: ineligible.
            ("ITEM-02", "ORD-1001", "COURT-CLASSIC", "40", 1, 8999,
             "delivered", _days_ago(5), 1, now),
            # Eligible, single unit in stock (sold-out and crash tests).
            ("ITEM-03", "ORD-1002", "TRAIL-BEAST", "42", 1, 14999,
             "delivered", _days_ago(3), 0, now),
            # Eligible, exactly two units in stock (concurrency test).
            ("ITEM-04", "ORD-1003", "COURT-CLASSIC", "44", 1, 8999,
             "delivered", _days_ago(2), 0, now),
            # Second eligible item on the same SKU/size pool as ITEM-04.
            ("ITEM-07", "ORD-1003", "COURT-CLASSIC", "44", 1, 8999,
             "delivered", _days_ago(2), 0, now),
            # Outside the return window: ineligible.
            ("ITEM-05", "ORD-1004", "AIRFLOW-RUNNER", "43", 1, 12999,
             "delivered", _days_ago(60), 0, now),
            # Eligible item with zero stock (insufficient-stock test).
            ("ITEM-06", "ORD-1005", "TRAIL-BEAST", "43", 1, 14999,
             "delivered", _days_ago(4), 0, now),
            # Shipped, not delivered: ineligible (benchmark denial case).
            ("ITEM-08", "ORD-1006", "COURT-CLASSIC", "41", 1, 8999,
             "shipped", _days_ago(2), 0, now),
        ],
    )
    stock: dict[tuple[str, str], int] = {}
    for sku in ("AIRFLOW-RUNNER", "COURT-CLASSIC"):
        for size in ("40", "41", "42", "43", "44", "45"):
            stock[(sku, size)] = 10 if sku == "AIRFLOW-RUNNER" else 5
    stock[("COURT-CLASSIC", "44")] = 2
    stock[("TRAIL-BEAST", "42")] = 1
    stock[("TRAIL-BEAST", "43")] = 0
    conn.executemany(
        "INSERT INTO stock (sku, size, on_hand, held) VALUES (?, ?, ?, 0)",
        [(sku, size, qty) for (sku, size), qty in sorted(stock.items())],
    )
