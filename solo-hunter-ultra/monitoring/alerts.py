"""Alert hooks."""

from __future__ import annotations

import structlog

LOGGER = structlog.get_logger(__name__)


def alert(message: str, **context: object) -> None:
    """Emit a structured alert log."""
    LOGGER.error("alert", message=message, **context)
