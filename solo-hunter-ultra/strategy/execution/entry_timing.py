"""Entry timing utilities."""

from __future__ import annotations


def urgency_ms(signal_seen_ms: float, now_ms: float) -> float:
    """Return elapsed milliseconds since signal detection."""
    return max(0.0, now_ms - signal_seen_ms)
