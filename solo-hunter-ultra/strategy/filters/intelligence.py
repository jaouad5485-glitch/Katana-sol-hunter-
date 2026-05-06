"""Layer 5 ML intelligence gate."""

from __future__ import annotations

from strategy.base import FilterResult


def validate_intelligence(score: float, min_confidence: float = 0.6) -> FilterResult:
    """Pass only opportunities whose model score clears the configured threshold."""
    if score < min_confidence:
        return FilterResult(False, "intelligence", "low_confidence", {"score": score})
    return FilterResult(True, "intelligence", metadata={"score": score})
