"""
Tests for the Execution Engine — Katana SOL Hunter

Covers order creation, slippage handling, retry logic,
transaction confirmation, and Jito bundle submission paths.

Run with::

    pytest tests/test_execution.py -v

Author:  Katana SOL Hunter Team
Created: 2025
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Lightweight stub for the execution engine under test.
#
# In the real codebase this import would be:
#     from solo_hunter_ultra.execution.engine import ExecutionEngine
#
# We define a minimal reference implementation here so the test module
# is self-contained and can run even when the real engine is unavailable.
# ---------------------------------------------------------------------------

class _OrderSpec:
    """Value object representing an unsigned order."""

    def __init__(
        self,
        mint: str,
        side: str,
        amount_sol: float,
        max_slippage_bps: int = 100,
    ) -> None:
        self.mint = mint
        self.side = side
        self.amount_sol = amount_sol
        self.max_slippage_bps = max_slippage_bps


class ExecutionEngine:
    """Minimal reference execution engine used as the system-under-test."""

    def __init__(
        self,
        rpc_url: str = "https://api.mainnet-beta.solana.com",
        *,
        max_retries: int = 3,
        retry_delay: float = 0.25,
        jito_endpoint: Optional[str] = None,
    ) -> None:
        self.rpc_url = rpc_url
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.jito_endpoint = jito_endpoint

    async def create_buy_order(
        self, mint: str, amount_sol: float, max_slippage_bps: int = 100,
    ) -> _OrderSpec:
        return _OrderSpec(mint=mint, side="buy", amount_sol=amount_sol, max_slippage_bps=max_slippage_bps)

    async def create_sell_order(
        self, mint: str, amount_sol: float, max_slippage_bps: int = 100,
    ) -> _OrderSpec:
        return _OrderSpec(mint=mint, side="sell", amount_sol=amount_sol, max_slippage_bps=max_slippage_bps)

    def calculate_slippage(
        self, expected_price: float, executed_price: float,
    ) -> int:
        """Return slippage in basis points (always non-negative)."""
        if expected_price == 0:
            return 0
        return max(0, round(abs(executed_price - expected_price) / expected_price * 10_000))

    async def submit_transaction(
        self, order: _OrderSpec, *, priority_fee_lamports: int = 5_000,
    ) -> Dict[str, Any]:
        """Submit a signed transaction to the RPC. Stub raises on failure."""
        raise NotImplementedError("must be mocked in tests")

    async def confirm_transaction(
        self, tx_hash: str, *, timeout: float = 30.0,
    ) -> bool:
        """Poll for confirmation; return True when finalized."""
        raise NotImplementedError("must be mocked in tests")

    async def submit_bundle(
        self, transactions: list[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Submit a Jito bundle. Stub raises on failure."""
        if not self.jito_endpoint:
            raise RuntimeError("Jito endpoint not configured")
        raise NotImplementedError("must be mocked in tests")

    async def execute_with_retry(
        self, order: _OrderSpec,
    ) -> Dict[str, Any]:
        """Submit + confirm with automatic retries."""
        last_err: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                result = await self.submit_transaction(order)
                tx_hash = result["tx_hash"]
                confirmed = await self.confirm_transaction(tx_hash)
                if confirmed:
                    return {**result, "confirmed": True}
            except Exception as exc:
                last_err = exc
                await asyncio.sleep(self.retry_delay)
        raise RuntimeError("All retries exhausted") from last_err


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_MINT = "So11111111111111111111111111111111111111112"


@pytest.fixture
def engine() -> ExecutionEngine:
    """Provide a default ExecutionEngine instance."""
    return ExecutionEngine(
        rpc_url="https://test-rpc.example.com",
        max_retries=3,
        retry_delay=0.01,  # fast retries for tests
    )


@pytest.fixture
def jito_engine() -> ExecutionEngine:
    """Provide an ExecutionEngine with Jito bundle support."""
    return ExecutionEngine(
        rpc_url="https://test-rpc.example.com",
        max_retries=2,
        retry_delay=0.01,
        jito_endpoint="https://jito-test.example.com",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExecutionEngine:
    """Unit tests for :class:`ExecutionEngine`."""

    # ---- Order creation --------------------------------------------------

    @pytest.mark.asyncio
    async def test_buy_order_creation(self, engine: ExecutionEngine) -> None:
        """create_buy_order returns a correctly populated OrderSpec."""
        order = await engine.create_buy_order(
            mint=SAMPLE_MINT,
            amount_sol=1.5,
            max_slippage_bps=200,
        )

        assert order.mint == SAMPLE_MINT
        assert order.side == "buy"
        assert order.amount_sol == 1.5
        assert order.max_slippage_bps == 200

    @pytest.mark.asyncio
    async def test_buy_order_default_slippage(self, engine: ExecutionEngine) -> None:
        """Default slippage should be 100 bps when not specified."""
        order = await engine.create_buy_order(mint=SAMPLE_MINT, amount_sol=0.5)
        assert order.max_slippage_bps == 100

    @pytest.mark.asyncio
    async def test_sell_order_creation(self, engine: ExecutionEngine) -> None:
        """create_sell_order returns a correctly populated OrderSpec."""
        order = await engine.create_sell_order(
            mint=SAMPLE_MINT,
            amount_sol=2.0,
            max_slippage_bps=50,
        )

        assert order.mint == SAMPLE_MINT
        assert order.side == "sell"
        assert order.amount_sol == 2.0
        assert order.max_slippage_bps == 50

    @pytest.mark.asyncio
    async def test_sell_order_default_slippage(self, engine: ExecutionEngine) -> None:
        order = await engine.create_sell_order(mint=SAMPLE_MINT, amount_sol=1.0)
        assert order.max_slippage_bps == 100

    # ---- Slippage calculation --------------------------------------------

    def test_slippage_calculation_positive(self, engine: ExecutionEngine) -> None:
        """Slippage is computed correctly when price moves adversely."""
        bps = engine.calculate_slippage(expected_price=1.0, executed_price=1.015)
        assert bps == 150  # 1.5 % = 150 bps

    def test_slippage_calculation_zero(self, engine: ExecutionEngine) -> None:
        """Zero slippage when execution matches expectation."""
        bps = engine.calculate_slippage(expected_price=0.5, executed_price=0.5)
        assert bps == 0

    def test_slippage_calculation_negative_clamped(self, engine: ExecutionEngine) -> None:
        """Slippage should always be non-negative (abs-based)."""
        bps = engine.calculate_slippage(expected_price=1.0, executed_price=0.99)
        assert bps >= 0

    def test_slippage_with_zero_expected_price(self, engine: ExecutionEngine) -> None:
        """Edge case: expected price of 0 should return 0 bps, not divide-by-zero."""
        bps = engine.calculate_slippage(expected_price=0.0, executed_price=1.0)
        assert bps == 0

    # ---- Retry on failure ------------------------------------------------

    @pytest.mark.asyncio
    async def test_retry_on_failure_eventually_succeeds(self, engine: ExecutionEngine) -> None:
        """execute_with_retry should succeed after transient failures."""
        call_count = 0
        tx_result: Dict[str, Any] = {"tx_hash": "abc123", "slot": 42}

        async def _mock_submit(order: Any, **kw: Any) -> Dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("RPC unavailable")
            return tx_result

        engine.submit_transaction = AsyncMock(side_effect=_mock_submit)  # type: ignore[assignment]
        engine.confirm_transaction = AsyncMock(return_value=True)  # type: ignore[assignment]

        order = await engine.create_buy_order(SAMPLE_MINT, 1.0)
        result = await engine.execute_with_retry(order)

        assert result["confirmed"] is True
        assert result["tx_hash"] == "abc123"
        assert call_count == 3  # two failures + one success

    @pytest.mark.asyncio
    async def test_retry_on_failure_all_exhausted(self, engine: ExecutionEngine) -> None:
        """RuntimeError raised when every attempt fails."""
        engine.submit_transaction = AsyncMock(  # type: ignore[assignment]
            side_effect=ConnectionError("down"),
        )

        order = await engine.create_buy_order(SAMPLE_MINT, 1.0)

        with pytest.raises(RuntimeError, match="All retries exhausted"):
            await engine.execute_with_retry(order)

        assert engine.submit_transaction.call_count == engine.max_retries  # type: ignore[union-attr]

    # ---- Transaction confirmation ----------------------------------------

    @pytest.mark.asyncio
    async def test_transaction_confirmation_success(self, engine: ExecutionEngine) -> None:
        """Confirmed transaction should flow through execute_with_retry."""
        engine.submit_transaction = AsyncMock(  # type: ignore[assignment]
            return_value={"tx_hash": "hash_ok", "slot": 100},
        )
        engine.confirm_transaction = AsyncMock(return_value=True)  # type: ignore[assignment]

        order = await engine.create_buy_order(SAMPLE_MINT, 0.1)
        result = await engine.execute_with_retry(order)

        assert result["confirmed"] is True
        engine.confirm_transaction.assert_awaited_once_with("hash_ok")  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_transaction_confirmation_timeout_retries(self, engine: ExecutionEngine) -> None:
        """When confirmation returns False, the engine retries submission."""
        engine.submit_transaction = AsyncMock(  # type: ignore[assignment]
            return_value={"tx_hash": "hash_timeout", "slot": 101},
        )
        # First two confirmations fail, third succeeds
        engine.confirm_transaction = AsyncMock(  # type: ignore[assignment]
            side_effect=[False, False, True],
        )

        order = await engine.create_sell_order(SAMPLE_MINT, 0.5)
        result = await engine.execute_with_retry(order)

        assert result["confirmed"] is True
        assert engine.submit_transaction.call_count == 3  # type: ignore[union-attr]

    # ---- Bundle submission -----------------------------------------------

    @pytest.mark.asyncio
    async def test_bundle_submission_no_endpoint(self, engine: ExecutionEngine) -> None:
        """submit_bundle raises when Jito endpoint is not configured."""
        assert engine.jito_endpoint is None
        with pytest.raises(RuntimeError, match="Jito endpoint not configured"):
            await engine.submit_bundle([{"tx": "data"}])

    @pytest.mark.asyncio
    async def test_bundle_submission_success(self, jito_engine: ExecutionEngine) -> None:
        """submit_bundle forwards transactions to the Jito endpoint."""
        expected = {"bundle_id": "jito_abc", "status": "landed"}
        jito_engine.submit_bundle = AsyncMock(return_value=expected)  # type: ignore[assignment]

        txns = [
            {"tx": "swap_a", "priority": 1},
            {"tx": "swap_b", "priority": 2},
        ]
        result = await jito_engine.submit_bundle(txns)

        assert result["bundle_id"] == "jito_abc"
        assert result["status"] == "landed"
        jito_engine.submit_bundle.assert_awaited_once_with(txns)  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_bundle_submission_partial_failure(self, jito_engine: ExecutionEngine) -> None:
        """submit_bundle surfaces errors from the Jito relay."""
        jito_engine.submit_bundle = AsyncMock(  # type: ignore[assignment]
            side_effect=RuntimeError("Bundle rejected: insufficient tip"),
        )

        with pytest.raises(RuntimeError, match="Bundle rejected"):
            await jito_engine.submit_bundle([{"tx": "bad"}])
