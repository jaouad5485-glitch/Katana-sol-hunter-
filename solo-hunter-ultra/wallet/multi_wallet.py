"""Multi-wallet round-robin rotation."""

from __future__ import annotations

from itertools import cycle


class MultiWallet:
    """Rotates wallets and tracks balances."""

    def __init__(self, wallets: list[str]) -> None:
        self._wallets = wallets
        self._cycle = cycle(wallets) if wallets else None
        self.balances: dict[str, float] = {wallet: 0.0 for wallet in wallets}

    def next_wallet(self) -> str:
        """Return the next wallet in round-robin order."""
        if self._cycle is None:
            raise RuntimeError("no wallets configured")
        return next(self._cycle)
