"""Kelly-based position sizing."""

from __future__ import annotations


def size_position(portfolio_sol: float, confidence: float, expected_multiple: float, max_fraction: float = 0.05, kelly_fraction: float = 0.25, min_trade_sol: float = 0.01, fee_reserve_sol: float = 0.02) -> float:
    """Calculate capped Kelly position size while reserving SOL for exits."""
    available = max(0.0, portfolio_sol - fee_reserve_sol)
    edge = max(0.0, (expected_multiple * confidence) - (1.0 - confidence))
    kelly = min(max_fraction, edge * kelly_fraction)
    size = available * kelly
    return 0.0 if size < min_trade_sol else min(size, available * max_fraction)
