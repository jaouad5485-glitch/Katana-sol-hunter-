"""SQLite schema management with TimescaleDB migration-compatible columns."""

from __future__ import annotations

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token_mint TEXT NOT NULL,
  dex TEXT NOT NULL,
  entry_price REAL,
  exit_price REAL,
  amount REAL,
  pnl REAL,
  tx_signature TEXT,
  status TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS opportunities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token_mint TEXT NOT NULL,
  confidence REAL,
  filters_passed TEXT,
  filters_failed TEXT,
  evaluated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS tokens (
  mint TEXT PRIMARY KEY,
  name TEXT,
  symbol TEXT,
  first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
  rug_status TEXT,
  dev_wallet TEXT
);
"""


async def init_db(path: str) -> None:
    """Initialize SQLite tables."""
    async with aiosqlite.connect(path) as db:
        await db.executescript(SCHEMA)
        await db.commit()
