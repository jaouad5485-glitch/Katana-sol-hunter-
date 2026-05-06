"""Micro-benchmark for the Phase 1 filter pipeline."""

from __future__ import annotations

import asyncio
from time import perf_counter

from intelligence.feature_engine import FeatureEngine
from intelligence.predictor import OnnxPredictor
from strategy.htf_sniper import HtfSniperStrategy

VALID_MINT = "So11111111111111111111111111111111111111112"


async def main() -> None:
    predictor = OnnxPredictor()
    await predictor.start()
    strategy = HtfSniperStrategy(FeatureEngine(), predictor)
    opportunity = {
        "token_mint": VALID_MINT,
        "pool_address": VALID_MINT,
        "dex": "raydium",
        "supply": 1_000_000,
        "liquidity_usd": 5_000,
        "lp_locked": True,
        "pool_age_slots": 1,
        "price": 0.001,
    }
    start = perf_counter()
    count = 1000
    await asyncio.gather(*(strategy.evaluate(opportunity) for _ in range(count)))
    elapsed_ms = (perf_counter() - start) * 1000
    print({"evaluations": count, "total_ms": elapsed_ms, "per_eval_ms": elapsed_ms / count})


if __name__ == "__main__":
    asyncio.run(main())
