"""Auto-reconnecting Solana WebSocket manager."""

from __future__ import annotations

import asyncio
import json
from itertools import count

import structlog
import websockets
from websockets.exceptions import ConnectionClosed

from core.event_bus import AsyncEventBus
from infrastructure.websocket.handlers import SUPPORTED_PROGRAMS, parse_program_log

LOGGER = structlog.get_logger(__name__)


class WebSocketManager:
    """Maintains Solana websocket subscriptions and emits listing events."""

    def __init__(self, endpoints: list[str], event_bus: AsyncEventBus, reconnect_interval: float = 1.0, max_attempts: int = 10) -> None:
        self._endpoints = endpoints
        self._event_bus = event_bus
        self._reconnect_interval = reconnect_interval
        self._max_attempts = max_attempts
        self._tasks: list[asyncio.Task[None]] = []
        self._running = False
        self.connected = False

    async def start(self) -> None:
        """Start websocket listeners for all configured endpoints."""
        self._running = True
        self._tasks = [asyncio.create_task(self._run_endpoint(endpoint)) for endpoint in self._endpoints]

    async def stop(self) -> None:
        """Stop websocket listeners."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self.connected = False

    async def _run_endpoint(self, endpoint: str) -> None:
        for attempt in count(1):
            if not self._running or attempt > self._max_attempts:
                return
            try:
                async with websockets.connect(endpoint, compression="deflate", ping_interval=15, close_timeout=1) as ws:
                    self.connected = True
                    await self._subscribe(ws)
                    async for message in ws:
                        payload = parse_program_log(message)
                        if payload:
                            self._event_bus.publish_nowait("token.listing.new", payload)
            except (OSError, ConnectionClosed, json.JSONDecodeError) as exc:
                self.connected = False
                LOGGER.warning("websocket_reconnect", endpoint=endpoint, attempt=attempt, error=str(exc))
                await asyncio.sleep(min(self._reconnect_interval * (2 ** (attempt - 1)), 30.0))

    async def _subscribe(self, ws: websockets.WebSocketClientProtocol) -> None:
        request_id = 1
        for program_id in SUPPORTED_PROGRAMS:
            await ws.send(json.dumps({
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "logsSubscribe",
                "params": [{"mentions": [program_id]}, {"commitment": "processed"}],
            }))
            request_id += 1
        await ws.send(json.dumps({"jsonrpc": "2.0", "id": request_id, "method": "blockSubscribe", "params": ["all"]}))
