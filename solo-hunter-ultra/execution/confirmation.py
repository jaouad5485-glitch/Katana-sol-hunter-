"""WebSocket-based confirmation tracking hooks."""

from __future__ import annotations

import asyncio


class ConfirmationTracker:
    """Tracks transaction confirmations with timeout."""

    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self._timeout = timeout_seconds
        self._events: dict[str, asyncio.Event] = {}

    async def wait(self, signature: str) -> bool:
        """Wait for a websocket signature confirmation."""
        event = self._events.setdefault(signature, asyncio.Event())
        try:
            await asyncio.wait_for(event.wait(), timeout=self._timeout)
            return True
        except TimeoutError:
            return False

    def mark_confirmed(self, signature: str) -> None:
        """Mark a signature as confirmed."""
        self._events.setdefault(signature, asyncio.Event()).set()
