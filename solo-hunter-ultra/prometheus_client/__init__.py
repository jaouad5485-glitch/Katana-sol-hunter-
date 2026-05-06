"""Minimal prometheus_client fallback for local tests."""

from __future__ import annotations

from typing import Any


class _Metric:
    """No-op metric that supports common Prometheus methods."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.value = 0.0

    def labels(self, *args: Any, **kwargs: Any) -> "_Metric":
        """Return self for labelled metrics."""
        return self

    def inc(self, amount: float = 1.0) -> None:
        """Increment the no-op value."""
        self.value += amount

    def set(self, value: float) -> None:
        """Set the no-op value."""
        self.value = value

    def observe(self, value: float) -> None:
        """Observe a no-op histogram value."""
        self.value = value


Counter = _Metric
Gauge = _Metric
Histogram = _Metric


def start_http_server(port: int) -> None:
    """No-op fallback server."""
