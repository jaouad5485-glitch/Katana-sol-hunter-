"""Priority fee estimation helpers."""

from __future__ import annotations


def estimate_priority_fee_lamports(congestion: float, base_lamports: int = 5_000) -> int:
    """Estimate a priority fee from normalized congestion."""
    return int(base_lamports * (1.0 + max(0.0, congestion)))
