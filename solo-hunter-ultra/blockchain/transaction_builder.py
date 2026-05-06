"""Fast transaction builder with cached instruction templates."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class TransactionDraft:
    """Serializable transaction draft used by execution components."""

    dex: str
    token_mint: str
    pool_address: str
    blockhash: str
    compute_unit_limit: int
    priority_fee_lamports: int
    instructions: list[dict[str, Any]]


class TransactionBuilder:
    """Builds deterministic swap transaction drafts with LRU account-meta cache."""

    def __init__(self, compute_unit_limit: int = 140_000, cache_size: int = 1000) -> None:
        self._compute_unit_limit = compute_unit_limit
        self._cache_size = cache_size
        self._account_meta_cache: OrderedDict[str, list[str]] = OrderedDict()

    def build_swap(self, opportunity: dict[str, Any], blockhash: str, priority_fee_lamports: int) -> TransactionDraft:
        """Build a DEX-specific swap draft from cached templates."""
        dex = str(opportunity["dex"])
        pool = str(opportunity["pool_address"])
        accounts = self._cached_accounts(pool, opportunity)
        return TransactionDraft(
            dex=dex,
            token_mint=str(opportunity["token_mint"]),
            pool_address=pool,
            blockhash=blockhash,
            compute_unit_limit=self._compute_unit_limit,
            priority_fee_lamports=priority_fee_lamports,
            instructions=[{"program": dex, "accounts": accounts, "data_template": "swap_exact_in"}],
        )

    def _cached_accounts(self, pool: str, opportunity: dict[str, Any]) -> list[str]:
        cached = self._account_meta_cache.get(pool)
        if cached:
            self._account_meta_cache.move_to_end(pool)
            return cached
        accounts = sorted([pool, str(opportunity["token_mint"]), str(opportunity.get("dev_wallet", ""))])
        self._account_meta_cache[pool] = accounts
        if len(self._account_meta_cache) > self._cache_size:
            self._account_meta_cache.popitem(last=False)
        return accounts
