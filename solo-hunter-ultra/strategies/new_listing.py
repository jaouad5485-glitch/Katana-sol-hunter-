"""New listing signal model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class NewListingSignal:
    """Normalized new token listing signal."""

    token_mint: str
    pool_address: str
    dex: str
    liquidity_usd: float
    dev_wallet: str
