"""Low-latency asyncio event bus for Solo-Hunter Ultra."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from time import time
from typing import Any
from uuid import uuid4

import structlog

EventHandler = Callable[["Event"], Awaitable[None]]
LOGGER = structlog.get_logger(__name__)


@dataclass(slots=True, frozen=True)
class Event:
    """Immutable event envelope carried through the async bus."""

    topic: str
    payload: dict[str, Any]
    event_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: float = field(default_factory=time)


class AsyncEventBus:
    """Async pub/sub bus backed by bounded queues and worker tasks."""

    def __init__(self, queue_size: int = 10_000, workers: int = 4) -> None:
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=queue_size)
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)
        self._workers = workers
        self._tasks: list[asyncio.Task[None]] = []
        self._running = asyncio.Event()

    def subscribe(self, topic: str, handler: EventHandler) -> None:
        """Register an async handler for a topic or wildcard prefix ending in '*'."""
        self._subscribers[topic].append(handler)

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish an event without blocking the hot path longer than queue insertion."""
        await self._queue.put(Event(topic=topic, payload=payload))

    def publish_nowait(self, topic: str, payload: dict[str, Any]) -> bool:
        """Best-effort publish for websocket hot paths; returns False on backpressure."""
        try:
            self._queue.put_nowait(Event(topic=topic, payload=payload))
            return True
        except asyncio.QueueFull:
            LOGGER.warning("event_bus_queue_full", topic=topic)
            return False

    async def start(self) -> None:
        """Start worker tasks."""
        self._running.set()
        self._tasks = [asyncio.create_task(self._worker(i)) for i in range(self._workers)]

    async def stop(self) -> None:
        """Drain and cancel workers."""
        self._running.clear()
        await self._queue.join()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def _worker(self, worker_id: int) -> None:
        while self._running.is_set():
            try:
                event = await self._queue.get()
                await self._dispatch(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.exception("event_dispatch_failed", worker_id=worker_id, error=str(exc))
            finally:
                if 'event' in locals():
                    self._queue.task_done()

    async def _dispatch(self, event: Event) -> None:
        handlers = self._matching_handlers(event.topic)
        if handlers:
            await asyncio.gather(*(handler(event) for handler in handlers), return_exceptions=False)

    def _matching_handlers(self, topic: str) -> list[EventHandler]:
        exact = list(self._subscribers.get(topic, ()))
        wildcard = [
            handler
            for pattern, handlers in self._subscribers.items()
            if pattern.endswith("*") and topic.startswith(pattern[:-1])
            for handler in handlers
        ]
        return exact + wildcard
