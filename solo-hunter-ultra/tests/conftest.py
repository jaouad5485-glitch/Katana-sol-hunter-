"""Pytest configuration and fixtures for Solo-Hunter Ultra tests."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Generator

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def reset_env() -> None:
    """Reset environment variables before each test."""
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def mock_settings() -> dict:
    """Provide mock settings for testing."""
    return {
        "bot": {
            "name": "Solo-Hunter Ultra",
            "mode": "test",
            "max_open_positions": 5,
            "max_daily_loss_sol": 1.0,
            "emergency_stop": True,
        },
        "rpc": {
            "endpoints": [
                {"url": "https://test-rpc.example.com", "weight": 1.0, "priority": 1}
            ],
            "timeout": 2.0,
            "max_connections": 10,
        },
        "redis": {
            "host": "localhost",
            "port": 6379,
            "db": 0,
            "decode_responses": False,
        },
        "position": {
            "max_position_size_sol": 0.5,
            "kelly_fraction": 0.25,
            "stop_loss_bps": 2000,
            "take_profit_levels": [20000, 30000, 50000, 100000],
        },
    }


@pytest.fixture
def sample_token_data() -> dict:
    """Provide sample token data for filter testing."""
    return {
        "mint": "Token123456789",
        "name": "Test Token",
        "symbol": "TEST",
        "decimals": 9,
        "total_supply": 1000000000,
        "mint_authority": None,
        "freeze_authority": None,
        "liquidity_usd": 50000.0,
        "transfer_tax_percent": 0.0,
        "is_meme": False,
        "renounced": True,
    }