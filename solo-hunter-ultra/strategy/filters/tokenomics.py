"""Layer 2 tokenomics validation."""

from __future__ import annotations

from strategy.base import FilterResult


def validate_tokenomics(token_info: dict[str, object], max_supply: int = 1_000_000_000_000_000_000) -> FilterResult:
    """Reject risky authorities and unreasonable supply values."""
    if token_info.get("mint_authority"):
        return FilterResult(False, "tokenomics", "mint_authority_present")
    if token_info.get("freeze_authority"):
        return FilterResult(False, "tokenomics", "freeze_authority_present")
    if token_info.get("program") not in {"spl-token", "token-2022", None}:
        return FilterResult(False, "tokenomics", "unsupported_token_program")
    supply = int(token_info.get("supply", 0) or 0)
    if supply <= 0 or supply > max_supply:
        return FilterResult(False, "tokenomics", "invalid_supply")
    return FilterResult(True, "tokenomics")
