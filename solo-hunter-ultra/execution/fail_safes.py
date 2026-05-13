"""Risk fail-safe controls."""

from __future__ import annotations

import asyncio
import structlog
from dataclasses import dataclass, field
from typing import Any

from solders.pubkey import Pubkey

LOGGER = structlog.get_logger(__name__)


@dataclass(slots=True)
class FailSafeConfig:
    """Fail-safe thresholds."""

    max_daily_loss_sol: float
    max_open_positions: int
    emergency_close_timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0


@dataclass
class Position:
    """Represents an open trading position."""

    mint: str
    amount: int
    entry_price: float
    entry_slot: int
    opened_at: float
    stop_loss: float | None = None
    take_profit: float | None = None


@dataclass
class CloseResult:
    """Result of an emergency close operation."""

    mint: str
    success: bool
    tx_signature: str | None = None
    error: str | None = None
    amount_closed: int = 0


class FailSafes:
    """Evaluates kill-switch conditions and emergency close triggers."""

    def __init__(
        self,
        config: FailSafeConfig,
        jito_client: Any | None = None,
        rpc_pool: Any | None = None,
    ) -> None:
        self._config = config
        self._jito = jito_client
        self._rpc = rpc_pool
        self.pnl_today_sol = 0.0
        self.open_positions: dict[str, Position] = {}
        self._emergency_in_progress = False
        self._close_results: list[CloseResult] = []

    def register_position(self, mint: str, amount: int, entry_price: float, entry_slot: int) -> None:
        """Register a new open position for tracking."""
        self.open_positions[mint] = Position(
            mint=mint,
            amount=amount,
            entry_price=entry_price,
            entry_slot=entry_slot,
            opened_at=asyncio.get_event_loop().time(),
        )
        LOGGER.info("position_registered", mint=mint, amount=amount, entry_price=entry_price)

    def close_position(self, mint: str) -> None:
        """Remove a position from tracking after successful close."""
        if mint in self.open_positions:
            del self.open_positions[mint]
            LOGGER.info("position_removed_from_tracking", mint=mint)

    def trading_allowed(self) -> bool:
        """Return whether new positions may be opened."""
        if self._emergency_in_progress:
            LOGGER.warning("trading_blocked_emergency_active")
            return False
        loss_ok = self.pnl_today_sol > -self._config.max_daily_loss_sol
        positions_ok = len(self.open_positions) < self._config.max_open_positions
        if not loss_ok:
            LOGGER.error("trading_blocked_daily_loss_limit", pnl_today=self.pnl_today_sol, limit=-self._config.max_daily_loss_sol)
        if not positions_ok:
            LOGGER.error("trading_blocked_max_positions", open=len(self.open_positions), max=self._config.max_open_positions)
        return loss_ok and positions_ok

    def update_pnl(self, pnl_delta: float) -> None:
        """Update daily PnL tracking."""
        self.pnl_today_sol += pnl_delta
        LOGGER.info("pnl_updated", pnl_today=self.pnl_today_sol, delta=pnl_delta)

    async def emergency_close_all(self) -> list[CloseResult]:
        """
        Execute emergency market sell for all open positions.
        
        This is the critical fail-safe that protects against catastrophic losses.
        It will attempt to close ALL open positions by selling at market price
        through Jito bundles for fastest execution.
        
        Returns:
            List of CloseResult for each position attempted.
        """
        if self._emergency_in_progress:
            LOGGER.warning("emergency_close_already_in_progress")
            return self._close_results

        if not self.open_positions:
            LOGGER.info("no_open_positions_to_close")
            return []

        self._emergency_in_progress = True
        self._close_results = []
        LOGGER.critical("emergency_close_initiated", positions=len(self.open_positions))

        close_tasks = [
            self._emergency_close_position(mint, position)
            for mint, position in list(self.open_positions.items())
        ]

        results = await asyncio.gather(*close_tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                LOGGER.error("emergency_close_task_failed", error=str(result))
                self._close_results.append(CloseResult(mint="unknown", success=False, error=str(result)))
            elif isinstance(result, CloseResult):
                self._close_results.append(result)

        success_count = sum(1 for r in self._close_results if r.success)
        LOGGER.critical("emergency_close_completed", total=len(self._close_results), successful=success_count)

        return self._close_results

    async def _emergency_close_position(self, mint: str, position: Position) -> CloseResult:
        """Execute emergency close for a single position with retries."""
        for attempt in range(self._config.max_retries):
            try:
                LOGGER.info("attempting_emergency_close", mint=mint, attempt=attempt + 1, amount=position.amount)

                tx_sig = await self._execute_market_sell(mint, position.amount)

                if tx_sig:
                    self.close_position(mint)
                    LOGGER.critical("position_closed_successfully", mint=mint, tx=tx_sig)
                    return CloseResult(
                        mint=mint,
                        success=True,
                        tx_signature=tx_sig,
                        amount_closed=position.amount,
                    )
            except Exception as exc:
                LOGGER.error("emergency_close_attempt_failed", mint=mint, attempt=attempt + 1, error=str(exc))
                if attempt < self._config.max_retries - 1:
                    await asyncio.sleep(self._config.retry_delay * (attempt + 1))

        LOGGER.error("emergency_close_all_attempts_exhausted", mint=mint, amount=position.amount)
        return CloseResult(
            mint=mint,
            success=False,
            error=f"Failed after {self._config.max_retries} attempts",
            amount_closed=0,
        )

    async def _execute_market_sell(self, mint: str, amount: int) -> str | None:
        """
        Execute a market sell transaction for the given mint.
        
        This constructs a Jupiter swap transaction to sell the token for SOL
        at the best available market price. Uses Jito for accelerated inclusion.
        
        Args:
            mint: Token mint address to sell
            amount: Amount of tokens to sell (in lamports/smallest unit)
            
        Returns:
            Transaction signature if successful, None otherwise.
        """
        if not self._jito or not self._rpc:
            LOGGER.error("emergency_sell_requires_jito_and_rpc", has_jito=bool(self._jito), has_rpc=bool(self._rpc))
            return None

        try:
            jupiter_url = f"https://quote-api.jup.ag/v6/quote?inputMint={mint}&outputMint=So11111111111111111111111111111111111111112&amount={amount}&slippageBps=50&onlyDirectRoutes=false"

            async with asyncio.timeout(10.0):
                import httpx
                async with httpx.AsyncClient() as client:
                    quote_resp = await client.get(jupiter_url)
                    quote_data = quote_resp.json()

                    if "outAmount" not in quote_data:
                        LOGGER.error("jupiter_quote_failed", mint=mint, response=quote_data)
                        return None

                    swap_resp = await client.post(
                        "https://quote-api.jup.ag/v6/swap",
                        json={
                            "quoteResponse": quote_data,
                            "userPublicKey": str(self._wallet_pubkey) if hasattr(self, "_wallet_pubkey") else "placeholder",
                            "wrapAndUnwrapSol": True,
                        },
                    )
                    swap_data = swap_resp.json()

                    if "swapTransaction" not in swap_data:
                        LOGGER.error("jupiter_swap_failed", mint=mint)
                        return None

                    tx_bytes = bytes.fromhex(swap_data["swapTransaction"])
                    tx_sig = await self._jito.submit_bundle([tx_bytes], wait_for_confirmation=True)

                    return tx_sig

        except asyncio.TimeoutError:
            LOGGER.error("jupiter_api_timeout", mint=mint)
            return None
        except Exception as exc:
            LOGGER.error("market_sell_execution_failed", mint=mint, error=str(exc))
            return None

    def get_status(self) -> dict[str, Any]:
        """Get current fail-safe status for monitoring."""
        return {
            "emergency_in_progress": self._emergency_in_progress,
            "open_positions": len(self.open_positions),
            "pnl_today_sol": self.pnl_today_sol,
            "max_daily_loss_sol": self._config.max_daily_loss_sol,
            "max_open_positions": self._config.max_open_positions,
            "trading_allowed": self.trading_allowed(),
            "close_results": [
                {"mint": r.mint, "success": r.success, "tx": r.tx_signature, "error": r.error}
                for r in self._close_results
            ],
        }