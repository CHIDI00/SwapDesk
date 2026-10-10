"""SQLite persistence and transaction helpers.

All business writes go through a single IMMEDIATE transaction owned by the
calling operation. Connections are short-lived: one per operation call, so
concurrent writers serialize in SQLite instead of sharing cursor state.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY,
  customer_ref TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS order_items (
  id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL REFERENCES orders(id),
  sku TEXT NOT NULL,
  size TEXT NOT NULL,
  qty INTEGER NOT NULL CHECK (qty > 0),
  price_cents INTEGER NOT NULL,
  status TEXT NOT NULL,
  delivered_at TEXT,
  final_sale INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stock (
  sku TEXT NOT NULL,
  size TEXT NOT NULL,
  on_hand INTEGER NOT NULL CHECK (on_hand >= 0),
  held INTEGER NOT NULL DEFAULT 0 CHECK (held >= 0),
  PRIMARY KEY (sku, size)
);
CREATE TABLE IF NOT EXISTS exchanges (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  order_id TEXT NOT NULL,
  order_item_id TEXT NOT NULL,
  requested_size TEXT NOT NULL,
  authorized_size TEXT NOT NULL,
  qty INTEGER NOT NULL CHECK (qty > 0),
  status TEXT NOT NULL,
  hold_released INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_active_exchange_item
  ON exchanges(order_item_id)
  WHERE status NOT IN ('cancelled', 'denied', 'arranged', 'escalated');
CREATE TABLE IF NOT EXISTS returns (
  id TEXT PRIMARY KEY,
  exchange_id TEXT NOT NULL REFERENCES exchanges(id),
  case_id TEXT NOT NULL,
  order_item_id TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS labels (
  id TEXT PRIMARY KEY,
  return_id TEXT NOT NULL REFERENCES returns(id),
  exchange_id TEXT NOT NULL REFERENCES exchanges(id),
  tracking_ref TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cases (
  case_id TEXT PRIMARY KEY,
  state TEXT NOT NULL,
  progress_json TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operations (
  idempotency_key TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  op_type TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL,
  result_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS journal (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  op_key TEXT NOT NULL,
  event TEXT NOT NULL,
  details_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_journal_op ON journal(op_key);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: str | Path, timeout: float = 10.0) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=timeout, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


@contextmanager
def immediate(conn: sqlite3.Connection) -> Iterator[None]:
    """Run the block in a single IMMEDIATE write transaction."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
