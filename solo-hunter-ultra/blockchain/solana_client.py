"""Solana client facade over the RPC pool."""

from __future__ import annotations

from typing import Any

from infrastructure.rpc.connection_pool import RpcConnectionPool


class SolanaClient:
    """Async Solana RPC facade for batch account fetching and simulation."""

    def __init__(self, rpc_pool: RpcConnectionPool) -> None:
        self._rpc = rpc_pool

    async def get_multiple_accounts(self, pubkeys: list[str]) -> Any:
        """Fetch accounts in one RPC round-trip."""
        return await self._rpc.call("getMultipleAccounts", [pubkeys, {"encoding": "base64"}])
