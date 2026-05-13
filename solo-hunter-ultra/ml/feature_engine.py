"""SIMD-friendly feature extraction for ML scoring."""

from __future__ import annotations

from time import monotonic
from typing import Any

import numpy as np


class FeatureEngine:
    """Extracts and caches 50-dimensional feature vectors with a 5-second TTL."""

    def __init__(self, ttl_seconds: float = 5.0) -> None:
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[float, np.ndarray]] = {}

    async def extract(self, token_mint: str, context: dict[str, Any]) -> np.ndarray:
        """Return a 50-feature float32 vector for an opportunity."""
        cached = self._cache.get(token_mint)
        now = monotonic()
        if cached and now - cached[0] <= self._ttl:
            return cached[1]
        vector = np.zeros(50, dtype=np.float32)
        keys = [
            "liquidity_usd", "volume_1m", "fee_bps", "holder_count", "holder_concentration",
            "new_holder_ratio", "tx_count_1m", "buy_sell_ratio", "dev_tokens_created", "dev_rugs",
            "dev_avg_lifespan", "price_change_1m", "price_change_5m", "price_change_1h", "sol_price",
            "network_congestion", "pool_age_slots", "lp_locked_ratio", "market_cap", "social_score",
        ]
        for idx, key in enumerate(keys):
            vector[idx] = float(context.get(key, 0.0) or 0.0)
        self._cache[token_mint] = (now, vector)
        return vector
