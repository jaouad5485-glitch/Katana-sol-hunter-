"""Binary Redis cache layer using msgpack serialization."""

from __future__ import annotations

from typing import Any

import msgpack
import redis.asyncio as redis


class RedisCache:
    """Thin async Redis wrapper with binary msgpack payloads."""

    def __init__(self, host: str, port: int, db: int = 0) -> None:
        self._client = redis.Redis(host=host, port=port, db=db, decode_responses=False)

    async def ping(self) -> bool:
        """Validate connectivity."""
        return bool(await self._client.ping())

    async def get(self, key: str) -> Any | None:
        """Read and unpack a cached value."""
        data = await self._client.get(key)
        if data is None:
            return None
        return msgpack.unpackb(data, raw=False)

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Pack and write a value with optional TTL."""
        payload = msgpack.packb(value, use_bin_type=True)
        await self._client.set(key, payload, ex=ttl_seconds)

    async def close(self) -> None:
        """Close Redis connections."""
        await self._client.aclose()
