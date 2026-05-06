"""Unit tests for cascading filter layers."""

from __future__ import annotations

from strategy.filters.basic_validation import validate_basic
from strategy.filters.intelligence import validate_intelligence
from strategy.filters.liquidity import validate_liquidity
from strategy.filters.rug_detection import validate_rug_risk
from strategy.filters.tokenomics import validate_tokenomics

VALID_MINT = "So11111111111111111111111111111111111111112"


def test_basic_validation_accepts_supported_dex() -> None:
    result = validate_basic({"token_mint": VALID_MINT, "pool_address": VALID_MINT, "dex": "raydium"})
    assert result.passed


def test_basic_validation_rejects_invalid_pubkey() -> None:
    result = validate_basic({"token_mint": "bad", "pool_address": VALID_MINT, "dex": "raydium"})
    assert not result.passed
    assert result.reason == "invalid_pubkey"


def test_tokenomics_rejects_mint_authority() -> None:
    result = validate_tokenomics({"mint_authority": "abc", "freeze_authority": None, "supply": 10})
    assert not result.passed


def test_liquidity_requires_locked_or_burned_lp() -> None:
    result = validate_liquidity({"liquidity_usd": 2000, "pool_age_slots": 1, "price": 1})
    assert not result.passed
    assert result.reason == "lp_not_locked_or_burned"


def test_rug_detection_rejects_honeypot() -> None:
    result = validate_rug_risk({"honeypot": True})
    assert not result.passed


def test_intelligence_threshold() -> None:
    assert validate_intelligence(0.7).passed
    assert not validate_intelligence(0.2).passed
