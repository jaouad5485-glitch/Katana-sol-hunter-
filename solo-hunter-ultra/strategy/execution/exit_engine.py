"""Exit rules for sniper positions."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ExitPlan:
    """Configurable exit strategy."""

    take_profit_levels_bps: list[int] = field(default_factory=lambda: [20000, 30000, 50000, 100000])
    stop_loss_bps: int = 2000
    trailing_activation_bps: int = 30000
    trailing_distance_bps: int = 15000


class ExitEngine:
    """Evaluates take-profit, stop-loss, trailing, and time exits."""

    def __init__(self, plan: ExitPlan | None = None) -> None:
        self._plan = plan or ExitPlan()

    def should_exit(self, pnl_bps: int, inactive_seconds: float, peak_bps: int) -> bool:
        """Return True when a sell rule triggers."""
        if pnl_bps <= -self._plan.stop_loss_bps:
            return True
        if inactive_seconds >= 3600:
            return True
        if peak_bps >= self._plan.trailing_activation_bps and pnl_bps <= peak_bps - self._plan.trailing_distance_bps:
            return True
        return False
