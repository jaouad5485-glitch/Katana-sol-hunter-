"""Durable nonce management."""

from __future__ import annotations


class NonceManager:
    """Tracks durable nonce accounts for advanced transaction flows."""

    def __init__(self) -> None:
        self._nonces: dict[str, str] = {}

    def set_nonce(self, wallet: str, nonce: str) -> None:
        """Store a wallet nonce."""
        self._nonces[wallet] = nonce

    def get_nonce(self, wallet: str) -> str | None:
        """Return a wallet nonce if present."""
        return self._nonces.get(wallet)
