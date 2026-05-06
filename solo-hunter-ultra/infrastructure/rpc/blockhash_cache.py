"""Aggressive recent blockhash cache for fast transaction construction."""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

import structlog

from infrastructure.redis.cache import RedisCache
from infrastructure.rpc.connection_pool import RpcConnectionPool

LOGGER = structlog.get_logger(__name__)


class BlockhashCache:
    """Keeps the latest Solana blockhashes warm in memory and Redis."""

    def __init__(self, rpc_pool: RpcConnectionPool, redis_cache: RedisCache | None = None, refresh_seconds: float = 2.0) -> None:
        self._rpc_pool = rpc_pool
        self._redis = redis_cache
        self._refresh_seconds = refresh_seconds
        self._hashes: deque[dict[str, Any]] = deque(maxlen=100)
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        """Prefetch the first blockhash and start the refresh loop."""
        self._running = True
        await self.refresh()
        self._task = asyncio.create_task(self._refresh_loop())

    async def stop(self) -> None:
        """Stop background refresh."""
        self._running = False
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def latest(self) -> dict[str, Any]:
        """Return the freshest cached blockhash, falling back to RPC on miss."""
        if self._hashes:
            return self._hashes[-1]
        if self._redis:
            cached = await self._redis.get("blockhash:latest")
            if cached:
                return cached
        return await self.refresh()

    async def refresh(self) -> dict[str, Any]:
        """Fetch and store the latest blockhash."""
        result = await self._rpc_pool.call("getLatestBlockhash", [{"commitment": "processed"}])
        value = result["value"] if isinstance(result, dict) and "value" in result else result
        self._hashes.append(value)
        if self._redis:
            await self._redis.set("blockhash:latest", value, ttl_seconds=20)
        return value

    async def invalidate_from_slot(self, slot: int) -> None:
        """Handle websocket block notifications by trimming stale hashes."""
        LOGGER.debug("blockhash_invalidation", slot=slot)
        await self.refresh()

    async def _refresh_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self._refresh_seconds)
            try:
                await self.refresh()
            except Exception as exc:
                LOGGER.warning("blockhash_refresh_failed", error=str(exc))
