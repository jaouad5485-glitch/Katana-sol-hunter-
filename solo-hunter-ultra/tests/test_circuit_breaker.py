"""Tests for circuit breaker and engine lifecycle management."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock
from time import monotonic

import pytest

from core.lifecycle import CircuitBreaker, EngineState


class TestEngineState:
    """Tests for EngineState enum."""

    def test_state_values(self) -> None:
        """Test all engine states are defined."""
        assert EngineState.INITIALIZING.value == "INITIALIZING"
        assert EngineState.WARMING_UP.value == "WARMING_UP"
        assert EngineState.ACTIVE.value == "ACTIVE"
        assert EngineState.DEGRADED.value == "DEGRADED"
        assert EngineState.SHUTDOWN.value == "SHUTDOWN"

    def test_state_is_string_enum(self) -> None:
        """Test engine state is a string enum."""
        for state in EngineState:
            assert isinstance(state.value, str)


class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""

    @pytest.fixture
    def breaker(self) -> CircuitBreaker:
        """Create circuit breaker for testing."""
        return CircuitBreaker(name="test_breaker")

    def test_initial_state(self, breaker: CircuitBreaker) -> None:
        """Test circuit breaker initial state."""
        assert breaker.opened_at is None
        assert breaker.failures == 0
        assert breaker.allow_request() is True
        assert breaker.is_open is False

    def test_record_success(self, breaker: CircuitBreaker) -> None:
        """Test recording success resets failures."""
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.failures == 2
        breaker.record_success()
        assert breaker.failures == 0
        assert breaker.opened_at is None
        assert breaker.allow_request() is True

    def test_single_failure_keeps_closed(self, breaker: CircuitBreaker) -> None:
        """Test single failure doesn't open circuit."""
        breaker.record_failure()
        assert breaker.failures == 1
        assert breaker.is_open is False
        assert breaker.allow_request() is True

    def test_threshold_exceeded_opens_circuit(self, breaker: CircuitBreaker) -> None:
        """Test circuit opens when failure threshold exceeded."""
        for _ in range(5):
            breaker.record_failure()
        assert breaker.is_open is True
        assert breaker.opened_at is not None
        assert breaker.failures >= 5

    def test_record_failure_below_threshold(self, breaker: CircuitBreaker) -> None:
        """Test failures below threshold don't open circuit."""
        for i in range(4):
            breaker.record_failure()
            assert breaker.failures == i + 1
            assert breaker.is_open is False

    def test_allow_request_false_when_open(self, breaker: CircuitBreaker) -> None:
        """Test allow_request returns False when circuit is open."""
        for _ in range(5):
            breaker.record_failure()
        assert breaker.is_open is True
        assert breaker.allow_request() is False

    def test_recovery_after_timeout(self, breaker: CircuitBreaker) -> None:
        """Test circuit allows request after recovery timeout."""
        for _ in range(5):
            breaker.record_failure()
        assert breaker.is_open is True
        breaker.opened_at = monotonic() - 20.0
        assert breaker.allow_request() is True

    def test_name_property(self, breaker: CircuitBreaker) -> None:
        """Test circuit breaker has correct name."""
        assert breaker.name == "test_breaker"

    def test_failure_threshold_default(self) -> None:
        """Test default failure threshold is 5."""
        breaker = CircuitBreaker(name="default_test")
        assert breaker.failure_threshold == 5

    def test_failure_threshold_custom(self) -> None:
        """Test custom failure threshold."""
        breaker = CircuitBreaker(name="custom_test", failure_threshold=10)
        assert breaker.failure_threshold == 10

    def test_recovery_timeout_default(self) -> None:
        """Test default recovery timeout is 15 seconds."""
        breaker = CircuitBreaker(name="timeout_test")
        assert breaker.recovery_timeout_seconds == 15.0

    def test_recovery_timeout_custom(self) -> None:
        """Test custom recovery timeout."""
        breaker = CircuitBreaker(name="timeout_test", recovery_timeout_seconds=60.0)
        assert breaker.recovery_timeout_seconds == 60.0

    def test_multiple_breakers_independent(self) -> None:
        """Test multiple circuit breakers operate independently."""
        breaker_a = CircuitBreaker(name="breaker_a", failure_threshold=3)
        breaker_b = CircuitBreaker(name="breaker_b", failure_threshold=5)
        for _ in range(3):
            breaker_a.record_failure()
        breaker_b.record_success()
        breaker_b.record_success()
        assert breaker_a.is_open is True
        assert breaker_b.is_open is False
        assert breaker_b.failures == 0

    def test_reopen_after_recovery_failure(self, breaker: CircuitBreaker) -> None:
        """Test circuit reopens if failure occurs during recovery period."""
        for _ in range(5):
            breaker.record_failure()
        assert breaker.is_open is True
        old_opened_at = breaker.opened_at
        breaker.record_failure()
        assert breaker.opened_at == old_opened_at

    def test_failure_count_tracking(self, breaker: CircuitBreaker) -> None:
        """Test failure count is properly tracked."""
        assert breaker.failures == 0
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.failures == 3

    def test_is_open_property(self, breaker: CircuitBreaker) -> None:
        """Test is_open property reflects circuit state."""
        assert breaker.is_open is False
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.is_open is True

    def test_success_clears_opened_at(self, breaker: CircuitBreaker) -> None:
        """Test success clears opened_at timestamp."""
        for _ in range(5):
            breaker.record_failure()
        assert breaker.opened_at is not None
        breaker.record_success()
        assert breaker.opened_at is None

    def test_recovery_window_respected(self, breaker: CircuitBreaker) -> None:
        """Test allow_request respects recovery timeout."""
        for _ in range(5):
            breaker.record_failure()
        breaker.opened_at = monotonic() - 5.0
        assert breaker.allow_request() is False
        breaker.opened_at = monotonic() - 16.0
        assert breaker.allow_request() is True

    def test_immediate_open_at_threshold(self, breaker: CircuitBreaker) -> None:
        """Test circuit opens immediately when threshold reached."""
        assert breaker.opened_at is None
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.opened_at is None
        breaker.record_failure()
        assert breaker.opened_at is not None