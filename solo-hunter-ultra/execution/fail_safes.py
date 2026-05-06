"""Risk fail-safe controls."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FailSafeConfig:
    """Fail-safe thresholds."""

    max_daily_loss_sol: float
    max_open_positions: int


class FailSafes:
    """Evaluates kill-switch conditions and emergency close triggers."""

    def __init__(self, config: FailSafeConfig) -> None:
        self._config = config
        self.pnl_today_sol = 0.0
        self.open_positions = 0

    def trading_allowed(self) -> bool:
        """Return whether new positions may be opened."""
        return self.pnl_today_sol > -self._config.max_daily_loss_sol and self.open_positions < self._config.max_open_positions

    async def emergency_close_all(self) -> None:
        """Placeholder for market-selling all open positions."""
        self.open_positions = 0
