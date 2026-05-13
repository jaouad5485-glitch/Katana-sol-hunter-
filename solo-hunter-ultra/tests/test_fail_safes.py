"""Tests for fail-safe risk management controls."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from execution.fail_safes import (
    CloseResult,
    FailSafeConfig,
    FailSafes,
    Position,
)


class TestFailSafeConfig:
    """Tests for FailSafeConfig dataclass."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = FailSafeConfig(max_daily_loss_sol=1.0, max_open_positions=10)
        assert config.max_daily_loss_sol == 1.0
        assert config.max_open_positions == 10
        assert config.emergency_close_timeout == 30.0
        assert config.max_retries == 3
        assert config.retry_delay == 1.0

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = FailSafeConfig(
            max_daily_loss_sol=5.0,
            max_open_positions=20,
            emergency_close_timeout=60.0,
            max_retries=5,
            retry_delay=2.0,
        )
        assert config.max_daily_loss_sol == 5.0
        assert config.max_open_positions == 20
        assert config.emergency_close_timeout == 60.0
        assert config.max_retries == 5
        assert config.retry_delay == 2.0


class TestPosition:
    """Tests for Position dataclass."""

    def test_position_creation(self) -> None:
        """Test position creation with all fields."""
        position = Position(
            mint="token123",
            amount=1000000,
            entry_price=0.05,
            entry_slot=123456789,
            opened_at=1000.0,
            stop_loss=0.04,
            take_profit=0.10,
        )
        assert position.mint == "token123"
        assert position.amount == 1000000
        assert position.entry_price == 0.05
        assert position.entry_slot == 123456789
        assert position.opened_at == 1000.0
        assert position.stop_loss == 0.04
        assert position.take_profit == 0.10

    def test_position_default_stop_loss(self) -> None:
        """Test position with no stop loss."""
        position = Position(
            mint="token456",
            amount=500000,
            entry_price=0.10,
            entry_slot=987654321,
            opened_at=2000.0,
        )
        assert position.stop_loss is None
        assert position.take_profit is None


class TestCloseResult:
    """Tests for CloseResult dataclass."""

    def test_successful_close(self) -> None:
        """Test successful close result."""
        result = CloseResult(
            mint="token789",
            success=True,
            tx_signature="tx123abc",
            amount_closed=1000000,
        )
        assert result.mint == "token789"
        assert result.success is True
        assert result.tx_signature == "tx123abc"
        assert result.error is None
        assert result.amount_closed == 1000000

    def test_failed_close(self) -> None:
        """Test failed close result."""
        result = CloseResult(
            mint="token000",
            success=False,
            error="Connection timeout",
            amount_closed=0,
        )
        assert result.mint == "token000"
        assert result.success is False
        assert result.tx_signature is None
        assert result.error == "Connection timeout"
        assert result.amount_closed == 0


class TestFailSafes:
    """Tests for FailSafes class."""

    @pytest.fixture
    def config(self) -> FailSafeConfig:
        """Create test configuration."""
        return FailSafeConfig(
            max_daily_loss_sol=1.0,
            max_open_positions=5,
            max_retries=2,
            retry_delay=0.1,
        )

    @pytest.fixture
    def fail_safes(self, config: FailSafeConfig) -> FailSafes:
        """Create FailSafes instance for testing."""
        return FailSafes(config=config)

    def test_initial_state(self, fail_safes: FailSafes) -> None:
        """Test initial state of fail-safe system."""
        assert fail_safes.pnl_today_sol == 0.0
        assert len(fail_safes.open_positions) == 0
        assert not fail_safes._emergency_in_progress

    def test_trading_allowed_no_positions(self, fail_safes: FailSafes) -> None:
        """Test trading allowed when no positions open."""
        assert fail_safes.trading_allowed() is True

    def test_trading_blocked_max_positions(self, fail_safes: FailSafes) -> None:
        """Test trading blocked when max positions reached."""
        fail_safes.register_position("token1", 1000000, 0.05, 123)
        fail_safes.register_position("token2", 2000000, 0.06, 124)
        fail_safes.register_position("token3", 3000000, 0.07, 125)
        fail_safes.register_position("token4", 4000000, 0.08, 126)
        fail_safes.register_position("token5", 5000000, 0.09, 127)
        assert fail_safes.trading_allowed() is False

    def test_trading_blocked_daily_loss(self, fail_safes: FailSafes) -> None:
        """Test trading blocked when daily loss limit reached."""
        fail_safes.pnl_today_sol = -1.5
        assert fail_safes.trading_allowed() is False

    def test_trading_allowed_partial_loss(self, fail_safes: FailSafes) -> None:
        """Test trading still allowed with partial loss."""
        fail_safes.pnl_today_sol = -0.5
        assert fail_safes.trading_allowed() is True

    def test_register_position(self, fail_safes: FailSafes) -> None:
        """Test position registration."""
        fail_safes.register_position("tokenABC", 1500000, 0.075, 999)
        assert "tokenABC" in fail_safes.open_positions
        position = fail_safes.open_positions["tokenABC"]
        assert position.mint == "tokenABC"
        assert position.amount == 1500000
        assert position.entry_price == 0.075
        assert position.entry_slot == 999

    def test_close_position(self, fail_safes: FailSafes) -> None:
        """Test position removal."""
        fail_safes.register_position("tokenXYZ", 2000000, 0.10, 888)
        assert "tokenXYZ" in fail_safes.open_positions
        fail_safes.close_position("tokenXYZ")
        assert "tokenXYZ" not in fail_safes.open_positions

    def test_update_pnl(self, fail_safes: FailSafes) -> None:
        """Test PnL update."""
        fail_safes.update_pnl(0.5)
        assert fail_safes.pnl_today_sol == 0.5
        fail_safes.update_pnl(-0.3)
        assert fail_safes.pnl_today_sol == 0.2

    def test_get_status(self, fail_safes: FailSafes) -> None:
        """Test status reporting."""
        fail_safes.register_position("token1", 1000000, 0.05, 111)
        fail_safes.register_position("token2", 2000000, 0.06, 222)
        fail_safes.update_pnl(0.25)
        status = fail_safes.get_status()
        assert status["emergency_in_progress"] is False
        assert status["open_positions"] == 2
        assert status["pnl_today_sol"] == 0.25
        assert status["max_daily_loss_sol"] == 1.0
        assert status["max_open_positions"] == 5
        assert status["trading_allowed"] is True

    @pytest.mark.asyncio
    async def test_emergency_close_no_positions(self, fail_safes: FailSafes) -> None:
        """Test emergency close with no open positions."""
        results = await fail_safes.emergency_close_all()
        assert results == []
        assert fail_safes._emergency_in_progress is False

    @pytest.mark.asyncio
    async def test_emergency_close_blocks_trading(self, fail_safes: FailSafes) -> None:
        """Test that emergency close blocks trading."""
        fail_safes.register_position("token1", 1000000, 0.05, 111)
        assert fail_safes.trading_allowed() is True
        assert fail_safes._emergency_in_progress is False
        await fail_safes.emergency_close_all()
        assert fail_safes.trading_allowed() is False