"""Lifecycle primitives and circuit breakers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from time import monotonic


class EngineState(StrEnum):
    """Engine state machine states."""

    INITIALIZING = "INITIALIZING"
    WARMING_UP = "WARMING_UP"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    SHUTDOWN = "SHUTDOWN"


@dataclass(slots=True)
class CircuitBreaker:
    """Per-component circuit breaker with half-open recovery."""

    name: str
    failure_threshold: int = 5
    recovery_timeout_seconds: float = 15.0
    failures: int = 0
    opened_at: float | None = None

    def allow_request(self) -> bool:
        """Return whether a protected operation may be attempted."""
        if self.opened_at is None:
            return True
        return monotonic() - self.opened_at >= self.recovery_timeout_seconds

    def record_success(self) -> None:
        """Close breaker after a successful operation."""
        self.failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        """Increment failure count and open the breaker if the threshold is reached."""
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.opened_at = monotonic()

    @property
    def is_open(self) -> bool:
        """Return True when requests are currently blocked."""
        return self.opened_at is not None and not self.allow_request()
