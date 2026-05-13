"""
HTF Sniper Strategy Module — Katana SOL Hunter

Analyzes higher-time-frame (HTF) market structure on Solana DEX pairs
before sniping entries on lower time frames.  Designed to filter out
low-conviction setups by requiring confluence from 1H / 4H / 1D
candle context before any position is opened.

Author:  Katana SOL Hunter Team
Created: 2025
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class HTFTimeframe(str, Enum):
    """Supported higher-time-frame intervals."""
    ONE_HOUR = "1h"
    FOUR_HOUR = "4h"
    ONE_DAY = "1d"


class TrendBias(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class HTFSniperConfig:
    """Immutable configuration for the HTF sniper strategy."""

    # Which HTFs to evaluate (ordered coarse → fine)
    timeframes: Tuple[HTFTimeframe, ...] = (
        HTFTimeframe.ONE_DAY,
        HTFTimeframe.FOUR_HOUR,
        HTFTimeframe.ONE_HOUR,
    )

    # Minimum number of HTF timeframes that must agree on direction
    min_confluence_count: int = 2

    # EMA lengths used for trend detection on each HTF candle set
    fast_ema_length: int = 9
    slow_ema_length: int = 21

    # RSI filter — only enter when RSI is within this band
    rsi_period: int = 14
    rsi_lower_bound: float = 30.0
    rsi_upper_bound: float = 70.0

    # Volume spike multiplier relative to 20-period SMA of volume
    volume_spike_multiplier: float = 1.5

    # Max slippage (bps) tolerated on the snipe entry
    max_slippage_bps: int = 150

    # Position sizing — fraction of available SOL balance to risk
    risk_fraction: float = 0.02

    # Retry / timeout behaviour for on-chain execution
    max_retries: int = 3
    retry_delay_s: float = 0.5
    confirmation_timeout_s: float = 30.0


@dataclass
class HTFContext:
    """Snapshot of higher-time-frame analysis for a single token pair."""

    mint: str
    timestamp: float = field(default_factory=time.time)
    trend_biases: Dict[HTFTimeframe, TrendBias] = field(default_factory=dict)
    rsi_values: Dict[HTFTimeframe, float] = field(default_factory=dict)
    volume_spike_flags: Dict[HTFTimeframe, bool] = field(default_factory=dict)
    overall_bias: TrendBias = TrendBias.NEUTRAL
    confluence_score: int = 0


@dataclass
class EntryParams:
    """Calculated parameters for a snipe entry."""

    mint: str
    side: str  # "buy" | "sell"
    amount_sol: float
    expected_price: float
    max_slippage_bps: int
    stop_loss_price: float
    take_profit_price: float
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

class HTFSniperStrategy:
    """
    High-Time-Frame Sniper Strategy.

    Workflow
    --------
    1. ``analyze_htf_context``  — pull candle data for each configured HTF and
       derive trend bias, RSI, and volume-spike flags.
    2. ``should_enter``         — evaluate confluence across HTFs.
    3. ``calculate_entry_params`` — compute position size, SL / TP, slippage.
    4. ``execute_snipe``        — submit the swap transaction on-chain.
    """

    def __init__(
        self,
        config: Optional[HTFSniperConfig] = None,
        *,
        market_data_provider: Any = None,
        execution_engine: Any = None,
    ) -> None:
        self.config = config or HTFSniperConfig()
        self._market_data = market_data_provider
        self._execution = execution_engine
        self._active_contexts: Dict[str, HTFContext] = {}
        logger.info(
            "HTFSniperStrategy initialised — timeframes=%s, min_confluence=%d",
            [tf.value for tf in self.config.timeframes],
            self.config.min_confluence_count,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze_htf_context(self, mint: str) -> HTFContext:
        """
        Build an :class:`HTFContext` for *mint* by fetching candle data on
        every configured HTF and computing trend bias, RSI, and volume flags.

        Parameters
        ----------
        mint:
            SPL token mint address to analyse.

        Returns
        -------
        HTFContext
            Populated context object also cached in ``self._active_contexts``.
        """
        ctx = HTFContext(mint=mint)
        logger.debug("Analysing HTF context for %s …", mint)

        for tf in self.config.timeframes:
            try:
                candles = await self._fetch_candles(mint, tf)
                if not candles:
                    logger.warning("No candle data for %s on %s", mint, tf.value)
                    continue

                bias = self._compute_trend_bias(candles)
                rsi = self._compute_rsi(candles)
                vol_spike = self._detect_volume_spike(candles)

                ctx.trend_biases[tf] = bias
                ctx.rsi_values[tf] = rsi
                ctx.volume_spike_flags[tf] = vol_spike

            except Exception:
                logger.exception("Error analysing %s on %s", mint, tf.value)

        ctx.confluence_score = self._score_confluence(ctx)
        ctx.overall_bias = self._derive_overall_bias(ctx)
        self._active_contexts[mint] = ctx

        logger.info(
            "HTF context for %s — bias=%s, confluence=%d/%d",
            mint,
            ctx.overall_bias.value,
            ctx.confluence_score,
            len(self.config.timeframes),
        )
        return ctx

    async def should_enter(self, mint: str) -> bool:
        """
        Return ``True`` when the HTF context for *mint* meets the minimum
        confluence threshold **and** RSI is within the configured band.
        """
        ctx = self._active_contexts.get(mint)
        if ctx is None:
            ctx = await self.analyze_htf_context(mint)

        if ctx.confluence_score < self.config.min_confluence_count:
            logger.debug(
                "Confluence too low for %s (%d < %d)",
                mint,
                ctx.confluence_score,
                self.config.min_confluence_count,
            )
            return False

        # RSI guard — check the finest-grained HTF that has data
        for tf in reversed(self.config.timeframes):
            rsi = ctx.rsi_values.get(tf)
            if rsi is not None:
                if not (self.config.rsi_lower_bound <= rsi <= self.config.rsi_upper_bound):
                    logger.debug(
                        "RSI filter rejected %s (rsi=%.1f on %s)",
                        mint, rsi, tf.value,
                    )
                    return False
                break

        logger.info("Entry signal confirmed for %s", mint)
        return True

    async def calculate_entry_params(
        self,
        mint: str,
        available_balance_sol: float,
    ) -> EntryParams:
        """
        Compute position-sizing and risk parameters for a snipe entry.

        Parameters
        ----------
        mint:
            Target token mint address.
        available_balance_sol:
            Current SOL wallet balance available for trading.

        Returns
        -------
        EntryParams
            Ready-to-execute entry specification.

        Raises
        ------
        ValueError
            If no HTF context is available or balance is insufficient.
        """
        ctx = self._active_contexts.get(mint)
        if ctx is None:
            raise ValueError(f"No HTF context available for {mint}; call analyze_htf_context first")

        amount_sol = round(available_balance_sol * self.config.risk_fraction, 6)
        if amount_sol <= 0:
            raise ValueError("Insufficient balance for position sizing")

        current_price = await self._fetch_current_price(mint)
        side = "buy" if ctx.overall_bias == TrendBias.BULLISH else "sell"

        # Simple ATR-based SL / TP placeholders (2:1 R:R)
        risk_offset = current_price * 0.03  # 3 % default risk band
        if side == "buy":
            stop_loss = current_price - risk_offset
            take_profit = current_price + risk_offset * 2.0
        else:
            stop_loss = current_price + risk_offset
            take_profit = current_price - risk_offset * 2.0

        params = EntryParams(
            mint=mint,
            side=side,
            amount_sol=amount_sol,
            expected_price=current_price,
            max_slippage_bps=self.config.max_slippage_bps,
            stop_loss_price=round(stop_loss, 8),
            take_profit_price=round(take_profit, 8),
        )
        logger.info(
            "Entry params for %s — side=%s, size=%.4f SOL, price=%.8f",
            mint, side, amount_sol, current_price,
        )
        return params

    async def execute_snipe(self, params: EntryParams) -> Dict[str, Any]:
        """
        Submit the swap transaction on-chain with retry logic.

        Parameters
        ----------
        params:
            Entry parameters previously computed by :meth:`calculate_entry_params`.

        Returns
        -------
        dict
            Transaction result containing at least ``{"tx_hash": str, "status": str}``.

        Raises
        ------
        RuntimeError
            If all retry attempts are exhausted.
        """
        last_error: Optional[Exception] = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                logger.info(
                    "Snipe attempt %d/%d for %s (%s %.4f SOL @ %.8f)",
                    attempt,
                    self.config.max_retries,
                    params.mint,
                    params.side,
                    params.amount_sol,
                    params.expected_price,
                )
                result = await self._submit_transaction(params)
                tx_hash = result.get("tx_hash", "")

                confirmed = await self._await_confirmation(
                    tx_hash,
                    timeout=self.config.confirmation_timeout_s,
                )
                if confirmed:
                    logger.info("Snipe confirmed — tx=%s", tx_hash)
                    return {**result, "status": "confirmed"}

                logger.warning("Confirmation timed out for tx=%s", tx_hash)

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Snipe attempt %d failed: %s", attempt, exc,
                )
                await asyncio.sleep(self.config.retry_delay_s)

        raise RuntimeError(
            f"All {self.config.max_retries} snipe attempts exhausted for {params.mint}"
        ) from last_error

    # ------------------------------------------------------------------
    # Internals — market-data helpers
    # ------------------------------------------------------------------

    async def _fetch_candles(
        self, mint: str, timeframe: HTFTimeframe,
    ) -> List[Dict[str, float]]:
        """Fetch OHLCV candles from the injected market-data provider."""
        if self._market_data is None:
            logger.debug("No market-data provider; returning empty candles")
            return []
        return await self._market_data.get_candles(mint, timeframe.value)  # type: ignore[union-attr]

    async def _fetch_current_price(self, mint: str) -> float:
        if self._market_data is None:
            raise RuntimeError("Market-data provider not configured")
        return await self._market_data.get_price(mint)  # type: ignore[union-attr]

    # ------------------------------------------------------------------
    # Internals — indicator calculations
    # ------------------------------------------------------------------

    @staticmethod
    def _ema(values: List[float], length: int) -> List[float]:
        """Exponential moving average over *values*."""
        if not values:
            return []
        k = 2.0 / (length + 1)
        ema_vals: List[float] = [values[0]]
        for v in values[1:]:
            ema_vals.append(v * k + ema_vals[-1] * (1 - k))
        return ema_vals

    def _compute_trend_bias(self, candles: List[Dict[str, float]]) -> TrendBias:
        closes = [c["close"] for c in candles]
        if len(closes) < self.config.slow_ema_length:
            return TrendBias.NEUTRAL
        fast = self._ema(closes, self.config.fast_ema_length)
        slow = self._ema(closes, self.config.slow_ema_length)
        if fast[-1] > slow[-1]:
            return TrendBias.BULLISH
        elif fast[-1] < slow[-1]:
            return TrendBias.BEARISH
        return TrendBias.NEUTRAL

    def _compute_rsi(self, candles: List[Dict[str, float]]) -> float:
        closes = [c["close"] for c in candles]
        period = self.config.rsi_period
        if len(closes) < period + 1:
            return 50.0  # neutral fallback
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [max(d, 0.0) for d in deltas[-period:]]
        losses = [abs(min(d, 0.0)) for d in deltas[-period:]]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - 100.0 / (1.0 + rs)

    def _detect_volume_spike(self, candles: List[Dict[str, float]]) -> bool:
        volumes = [c.get("volume", 0.0) for c in candles]
        if len(volumes) < 21:
            return False
        sma_20 = sum(volumes[-21:-1]) / 20
        return volumes[-1] > sma_20 * self.config.volume_spike_multiplier

    # ------------------------------------------------------------------
    # Internals — confluence scoring
    # ------------------------------------------------------------------

    def _score_confluence(self, ctx: HTFContext) -> int:
        bullish = sum(1 for b in ctx.trend_biases.values() if b == TrendBias.BULLISH)
        bearish = sum(1 for b in ctx.trend_biases.values() if b == TrendBias.BEARISH)
        return max(bullish, bearish)

    @staticmethod
    def _derive_overall_bias(ctx: HTFContext) -> TrendBias:
        bullish = sum(1 for b in ctx.trend_biases.values() if b == TrendBias.BULLISH)
        bearish = sum(1 for b in ctx.trend_biases.values() if b == TrendBias.BEARISH)
        if bullish > bearish:
            return TrendBias.BULLISH
        if bearish > bullish:
            return TrendBias.BEARISH
        return TrendBias.NEUTRAL

    # ------------------------------------------------------------------
    # Internals — execution helpers
    # ------------------------------------------------------------------

    async def _submit_transaction(self, params: EntryParams) -> Dict[str, Any]:
        if self._execution is None:
            raise RuntimeError("Execution engine not configured")
        return await self._execution.submit_swap(
            mint=params.mint,
            side=params.side,
            amount_sol=params.amount_sol,
            max_slippage_bps=params.max_slippage_bps,
        )

    async def _await_confirmation(
        self, tx_hash: str, *, timeout: float = 30.0,
    ) -> bool:
        if self._execution is None:
            raise RuntimeError("Execution engine not configured")
        try:
            return await asyncio.wait_for(
                self._execution.confirm_transaction(tx_hash),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return False
