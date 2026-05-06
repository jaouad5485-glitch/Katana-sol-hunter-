"""Layer 1 basic validation filter."""

from __future__ import annotations

from strategy.base import FilterResult

SUPPORTED_DEXES = {"raydium", "orca", "pump_fun"}
_BASE58_ALPHABET = frozenset("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")


def validate_basic(opportunity: dict[str, object]) -> FilterResult:
    """Validate pubkey, metadata, and DEX support in the cheapest layer."""
    token_mint = str(opportunity.get("token_mint", ""))
    if not _is_solana_pubkey(token_mint):
        return FilterResult(False, "basic_validation", "invalid_pubkey")
    if not token_mint or not opportunity.get("pool_address"):
        return FilterResult(False, "basic_validation", "empty_metadata")
    if opportunity.get("dex") not in SUPPORTED_DEXES:
        return FilterResult(False, "basic_validation", "unsupported_dex")
    return FilterResult(True, "basic_validation")


def _is_solana_pubkey(value: str) -> bool:
    """Return True for a base58-encoded 32-byte Solana public key shape."""
    return 32 <= len(value) <= 44 and all(char in _BASE58_ALPHABET for char in value)
