"""Layer 3 liquidity validation."""

from __future__ import annotations

from strategy.base import FilterResult


def validate_liquidity(pool: dict[str, object], min_liquidity_usd: float = 1000.0) -> FilterResult:
    """Validate minimum liquidity, LP safety, pool age, and price sanity."""
    liquidity = float(pool.get("liquidity_usd", 0.0) or 0.0)
    if liquidity < min_liquidity_usd:
        return FilterResult(False, "liquidity", "below_min_liquidity")
    if not bool(pool.get("lp_locked", False) or pool.get("lp_burned", False)):
        return FilterResult(False, "liquidity", "lp_not_locked_or_burned")
    if int(pool.get("pool_age_slots", 0) or 0) <= 0:
        return FilterResult(False, "liquidity", "invalid_pool_age")
    price = float(pool.get("price", 0.0) or 0.0)
    if price <= 0 or price > 1_000_000:
        return FilterResult(False, "liquidity", "invalid_price")
    return FilterResult(True, "liquidity")
