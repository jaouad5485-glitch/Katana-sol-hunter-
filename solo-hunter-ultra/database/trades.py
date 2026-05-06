"""Trade repository."""

from __future__ import annotations

import aiosqlite


class TradeRepository:
    """Persists trade records."""

    def __init__(self, path: str) -> None:
        self._path = path

    async def insert_trade(self, token_mint: str, dex: str, amount: float, status: str) -> None:
        """Insert a trade record."""
        async with aiosqlite.connect(self._path) as db:
            await db.execute("INSERT INTO trades(token_mint, dex, amount, status) VALUES (?, ?, ?, ?)", (token_mint, dex, amount, status))
            await db.commit()
