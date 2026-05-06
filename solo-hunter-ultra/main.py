"""Application entrypoint for Solo-Hunter Ultra."""

from __future__ import annotations

import asyncio
import signal

import structlog
import uvloop

from core.engine import SoloHunterEngine

LOGGER = structlog.get_logger(__name__)


async def amain() -> None:
    """Start the engine and wait for termination signals."""
    engine = SoloHunterEngine()
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    await engine.start()
    await stop_event.wait()
    await engine.stop()


def main() -> None:
    """Install uvloop and run the async application."""
    uvloop.install()
    asyncio.run(amain())


if __name__ == "__main__":
    main()
