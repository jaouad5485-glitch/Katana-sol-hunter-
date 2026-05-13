"""Tests for Kelly-based position sizing logic."""

from __future__ import annotations

import pytest

from risk.position_sizing import size_position


class TestSizePosition:
    """Tests for position sizing function."""

    def test_basic_kelly_calculation(self) -> None:
        """Test basic Kelly position sizing with standard parameters."""
        result = size_position(
            portfolio_sol=10.0,
            confidence=0.7,
            expected_multiple=3.0,
        )
        assert result > 0
        assert result <= 0.5

    def test_zero_confidence(self) -> None:
        """Test position sizing with zero confidence."""
        result = size_position(
            portfolio_sol=10.0,
            confidence=0.0,
            expected_multiple=3.0,
        )
        assert result == 0.0

    def test_low_confidence_below_threshold(self) -> None:
        """Test position sizing with low confidence below edge threshold."""
        result = size_position(
            portfolio_sol=10.0,
            confidence=0.3,
            expected_multiple=1.5,
        )
        assert result == 0.0

    def test_min_trade_size_threshold(self) -> None:
        """Test minimum trade size enforcement."""
        small_portfolio = size_position(
            portfolio_sol=0.01,
            confidence=0.8,
            expected_multiple=4.0,
        )
        assert small_portfolio < 0.01

    def test_max_fraction_cap(self) -> None:
        """Test that position size respects max fraction cap."""
        result = size_position(
            portfolio_sol=100.0,
            confidence=1.0,
            expected_multiple=10.0,
            max_fraction=0.05,
        )
        assert result <= 5.0

    def test_kelly_fraction_reduces_size(self) -> None:
        """Test that Kelly fraction properly reduces position size."""
        full_kelly = size_position(
            portfolio_sol=10.0,
            confidence=0.8,
            expected_multiple=3.0,
            kelly_fraction=1.0,
        )
        quarter_kelly = size_position(
            portfolio_sol=10.0,
            confidence=0.8,
            expected_multiple=3.0,
            kelly_fraction=0.25,
        )
        assert quarter_kelly < full_kelly

    def test_fee_reserve_respected(self) -> None:
        """Test that fee reserve is properly deducted from available balance."""
        result = size_position(
            portfolio_sol=1.0,
            confidence=0.9,
            expected_multiple=5.0,
            fee_reserve_sol=0.1,
        )
        available_after_reserve = 0.9
        assert result <= available_after_reserve

    def test_custom_parameters(self) -> None:
        """Test position sizing with custom parameters."""
        result = size_position(
            portfolio_sol=50.0,
            confidence=0.85,
            expected_multiple=4.5,
            max_fraction=0.10,
            kelly_fraction=0.5,
            min_trade_sol=0.1,
            fee_reserve_sol=0.05,
        )
        assert result >= 0.1
        max_possible = 50.0 * 0.10
        assert result <= max_possible

    def test_high_confidence_high_expected_multiple(self) -> None:
        """Test sizing for high-quality opportunity."""
        result = size_position(
            portfolio_sol=25.0,
            confidence=0.95,
            expected_multiple=8.0,
        )
        assert result > 0.5

    def test_edge_calculation_negative(self) -> None:
        """Test edge calculation when expected multiple is low."""
        result = size_position(
            portfolio_sol=10.0,
            confidence=0.5,
            expected_multiple=1.2,
        )
        assert result == 0.0

    def test_zero_portfolio(self) -> None:
        """Test handling of zero portfolio."""
        result = size_position(
            portfolio_sol=0.0,
            confidence=0.9,
            expected_multiple=5.0,
        )
        assert result == 0.0

    def test_negative_available_after_fees(self) -> None:
        """Test behavior when fee reserve exceeds portfolio."""
        result = size_position(
            portfolio_sol=0.01,
            confidence=0.9,
            expected_multiple=5.0,
            fee_reserve_sol=0.02,
        )
        assert result == 0.0