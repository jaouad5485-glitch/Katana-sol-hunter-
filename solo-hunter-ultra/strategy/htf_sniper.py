"""Cascading HFT sniper strategy implementation."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from intelligence.feature_engine import FeatureEngine
from intelligence.predictor import OnnxPredictor
from monitoring.metrics import OPPORTUNITIES_FILTERED_TOTAL, OPPORTUNITY_EVAL_MS
from strategy.base import Strategy
from strategy.filters.basic_validation import validate_basic
from strategy.filters.intelligence import validate_intelligence
from strategy.filters.liquidity import validate_liquidity
from strategy.filters.rug_detection import validate_rug_risk
from strategy.filters.tokenomics import validate_tokenomics


class HtfSniperStrategy(Strategy):
    """Early-rejection strategy that gates opportunities through five layers."""

    def __init__(self, feature_engine: FeatureEngine, predictor: OnnxPredictor, min_confidence: float = 0.6) -> None:
        self._feature_engine = feature_engine
        self._predictor = predictor
        self._min_confidence = min_confidence

    async def evaluate(self, opportunity: dict[str, Any]) -> dict[str, Any] | None:
        """Evaluate an opportunity and return a candidate if all layers pass."""
        start = perf_counter()
        checks = (
            validate_basic(opportunity),
            validate_tokenomics(opportunity),
            validate_liquidity(opportunity),
            validate_rug_risk(opportunity),
        )
        for result in checks:
            if not result.passed:
                OPPORTUNITIES_FILTERED_TOTAL.labels(result.layer, result.reason).inc()
                return None
        features = await self._feature_engine.extract(str(opportunity["token_mint"]), opportunity)
        score = self._predictor.predict(features)
        intel = validate_intelligence(score, self._min_confidence)
        if not intel.passed:
            OPPORTUNITIES_FILTERED_TOTAL.labels(intel.layer, intel.reason).inc()
            return None
        OPPORTUNITY_EVAL_MS.observe((perf_counter() - start) * 1000)
        return {**opportunity, "confidence": score, "features": features.tolist()}
