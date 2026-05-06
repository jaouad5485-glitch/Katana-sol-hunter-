"""Retry orchestration for idempotent transaction sends."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


class RetryEngine:
    """Retries operations with exponential backoff and max-attempt caps."""

    def __init__(self, max_retries: int = 3) -> None:
        self._max_retries = max_retries

    async def run(self, operation: Callable[[], Awaitable[T]]) -> T:
        """Run an async operation with retry."""
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return await operation()
            except (TimeoutError, RuntimeError, OSError) as exc:
                last_error = exc
                if attempt >= self._max_retries:
                    break
                await asyncio.sleep(0.05 * (2**attempt))
        raise RuntimeError("operation failed after retries") from last_error
