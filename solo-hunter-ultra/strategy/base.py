"""Strategy base classes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FilterResult:
    """Result emitted by a filter layer."""

    passed: bool
    layer: str
    reason: str = "ok"
    metadata: dict[str, Any] = field(default_factory=dict)


class Strategy(ABC):
    """Abstract async strategy interface."""

    @abstractmethod
    async def evaluate(self, opportunity: dict[str, Any]) -> dict[str, Any] | None:
        """Evaluate and optionally return a trade candidate."""
