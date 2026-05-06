"""Whale movement signal model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class WhaleMovementSignal:
    """Large wallet activity signal."""

    wallet: str
    token_mint: str
    amount_sol: float
