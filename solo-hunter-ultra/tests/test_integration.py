"""Integration tests for the signal-to-candidate pipeline."""

from __future__ import annotations

import asyncio

from core.event_bus import AsyncEventBus, Event
from intelligence.feature_engine import FeatureEngine
from intelligence.predictor import OnnxPredictor
from strategy.htf_sniper import HtfSniperStrategy

VALID_MINT = "So11111111111111111111111111111111111111112"


def test_event_bus_pipeline_confirms_opportunity() -> None:
    async def scenario() -> list[dict[str, object]]:
        bus = AsyncEventBus(workers=1)
        predictor = OnnxPredictor()
        await predictor.start()
        strategy = HtfSniperStrategy(FeatureEngine(), predictor)
        confirmed: list[dict[str, object]] = []

        async def on_listing(event: Event) -> None:
            candidate = await strategy.evaluate(event.payload)
            if candidate:
                await bus.publish("opportunity.confirmed", candidate)

        async def on_confirmed(event: Event) -> None:
            confirmed.append(event.payload)

        bus.subscribe("token.listing.new", on_listing)
        bus.subscribe("opportunity.confirmed", on_confirmed)
        await bus.start()
        await bus.publish("token.listing.new", {
            "token_mint": VALID_MINT,
            "pool_address": VALID_MINT,
            "dex": "raydium",
            "supply": 1_000_000,
            "liquidity_usd": 5_000,
            "lp_locked": True,
            "pool_age_slots": 1,
            "price": 0.001,
        })
        await asyncio.sleep(0.05)
        await bus.stop()
        return confirmed

    result = asyncio.run(scenario())
    assert len(result) == 1
