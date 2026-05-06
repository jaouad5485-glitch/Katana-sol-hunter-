"""Small structlog-compatible fallback used when dependency installation is unavailable."""

from __future__ import annotations

import logging
from typing import Any


class _Logger:
    """Minimal structured logger adapter."""

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def info(self, event: str, **context: Any) -> None:
        """Log an info event."""
        self._logger.info("%s %s", event, context)

    def warning(self, event: str, **context: Any) -> None:
        """Log a warning event."""
        self._logger.warning("%s %s", event, context)

    def error(self, event: str, **context: Any) -> None:
        """Log an error event."""
        self._logger.error("%s %s", event, context)

    def debug(self, event: str, **context: Any) -> None:
        """Log a debug event."""
        self._logger.debug("%s %s", event, context)

    def exception(self, event: str, **context: Any) -> None:
        """Log an exception event."""
        self._logger.exception("%s %s", event, context)


def get_logger(name: str | None = None) -> _Logger:
    """Return a minimal logger compatible with structlog.get_logger."""
    return _Logger(name or __name__)


def configure(**kwargs: Any) -> None:
    """Accept structlog.configure calls."""
    logging.basicConfig(level=logging.INFO)


class processors:
    """Processor placeholders for structlog compatibility."""

    class TimeStamper:
        """Timestamp processor placeholder."""

        def __init__(self, fmt: str = "iso") -> None:
            self.fmt = fmt

    class JSONRenderer:
        """JSON renderer placeholder."""
