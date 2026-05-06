"""Adaptive Jito tip optimizer."""

from __future__ import annotations


def calculate_tip_lamports(confidence: float, congestion: float, urgency_ms: float, expected_profit_lamports: int, base_tip: int, max_percentage: float) -> int:
    """Calculate a capped Jito tip from confidence, congestion, urgency, and profit."""
    urgency_multiplier = 1.0 + max(0.0, 50.0 - urgency_ms) / 100.0
    raw_tip = int(base_tip * (1.0 + confidence + congestion) * urgency_multiplier)
    cap = int(expected_profit_lamports * (max_percentage / 100.0))
    return max(base_tip, min(raw_tip, cap if cap > 0 else raw_tip))
