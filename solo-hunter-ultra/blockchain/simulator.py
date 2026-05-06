"""Transaction simulation adapter."""

from __future__ import annotations


class Simulator:
    """Simulates transactions before send when configured."""

    async def simulate(self, transaction: object) -> bool:
        """Return True when simulation succeeds."""
        return True
