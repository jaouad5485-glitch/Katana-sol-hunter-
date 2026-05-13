"""Latency-aware async Solana RPC connection pool."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

import httpx
import structlog

LOGGER = structlog.get_logger(__name__)


class SecurityError(Exception):
    """Raised when security validation fails."""
    pass


@dataclass(slots=True)
class RpcEndpoint:
    """RPC endpoint health and latency state."""

    url: str
    weight: float = 1.0
    priority: int = 1
    healthy: bool = True
    latency_ms: float = 1_000.0
    failures: int = 0
    last_checked: float = field(default_factory=monotonic)


def _validate_https(url: str) -> str:
    """
    Validate that URL uses HTTPS for production security.
    
    Args:
        url: The RPC endpoint URL to validate.
        
    Returns:
        The validated URL if secure.
        
    Raises:
        SecurityError: If URL does not use HTTPS.
    """
    if not url.startswith("https://"):
        raise SecurityError(f"RPC endpoint must use HTTPS in production: {url}. Got: {url[:20]}...")
    return url


class RpcConnectionPool:
    """Multi-endpoint RPC pool with failover and latency-weighted selection."""

    def __init__(
        self,
        endpoints: list[dict[str, Any]],
        timeout: float = 2.0,
        max_connections: int = 50,
        enforce_https: bool = True,
    ) -> None:
        self._enforce_https = enforce_https
        self.endpoints = []
        for endpoint in endpoints:
            url = endpoint.get("url", "")
            if self._enforce_https:
                validated_url = _validate_https(url)
                LOGGER.info("rpc_endpoint_validated", url=validated_url, secure=True)
            else:
                validated_url = url
                LOGGER.warning("rpc_endpoint_https_disabled", url=url[:30], warning="HTTPS validation bypassed")
            endpoint["url"] = validated_url
            self.endpoints.append(RpcEndpoint(**endpoint))
        limits = httpx.Limits(max_connections=max_connections * max(1, len(self.endpoints)), max_keepalive_connections=max_connections)
        self._client = httpx.AsyncClient(http2=True, timeout=timeout, limits=limits)
        self._rr_index = 0
        self._health_task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        """Start periodic health checks."""
        self._running = True
        self._health_task = asyncio.create_task(self._health_loop())

    async def stop(self) -> None:
        """Stop health checks and close HTTP connections."""
        self._running = False
        if self._health_task:
            self._health_task.cancel()
            await asyncio.gather(self._health_task, return_exceptions=True)
        await self._client.aclose()

    async def call(self, method: str, params: list[Any] | None = None) -> Any:
        """Execute a JSON-RPC call against the best currently healthy endpoint."""
        endpoint = self._select_endpoint()
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
        start = monotonic()
        try:
            response = await self._client.post(endpoint.url, json=payload)
            response.raise_for_status()
            endpoint.latency_ms = (monotonic() - start) * 1000
            endpoint.failures = 0
            data = response.json()
            if "error" in data:
                raise RuntimeError(str(data["error"]))
            return data.get("result")
        except (httpx.HTTPError, RuntimeError) as exc:
            endpoint.failures += 1
            endpoint.healthy = endpoint.failures < 3
            LOGGER.warning("rpc_call_failed", endpoint=endpoint.url, method=method, error=str(exc))
            raise

    def _select_endpoint(self) -> RpcEndpoint:
        healthy = [endpoint for endpoint in self.endpoints if endpoint.healthy]
        if not healthy:
            raise RuntimeError("no healthy RPC endpoints")
        healthy.sort(key=lambda item: (item.priority, item.latency_ms / max(item.weight, 0.01)))
        selected = healthy[self._rr_index % min(2, len(healthy))]
        self._rr_index += 1
        return selected

    async def _health_loop(self) -> None:
        while self._running:
            await asyncio.gather(*(self._check_endpoint(endpoint) for endpoint in self.endpoints), return_exceptions=True)
            await asyncio.sleep(5)

    async def _check_endpoint(self, endpoint: RpcEndpoint) -> None:
        start = monotonic()
        try:
            payload = {"jsonrpc": "2.0", "id": 1, "method": "getHealth"}
            response = await self._client.post(endpoint.url, json=payload)
            response.raise_for_status()
            endpoint.healthy = True
            endpoint.failures = 0
            endpoint.latency_ms = (monotonic() - start) * 1000
        except httpx.HTTPError as exc:
            endpoint.failures += 1
            endpoint.healthy = False
            LOGGER.warning("rpc_health_failed", endpoint=endpoint.url, error=str(exc))
        finally:
            endpoint.last_checked = monotonic()
