"""Health checks for load balancers and supervisors."""

from __future__ import annotations

from aiohttp import web


class HealthServer:
    """Small HTTP health endpoint."""

    def __init__(self) -> None:
        self.status: dict[str, bool] = {"rpc": False, "websocket": False, "jito": False, "redis": False, "wallet": False}
        self._runner: web.AppRunner | None = None

    async def start(self, port: int = 8080) -> None:
        """Start /health endpoint."""
        app = web.Application()
        app.router.add_get("/health", self._handle)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", port)
        await site.start()

    async def stop(self) -> None:
        """Stop health endpoint."""
        if self._runner:
            await self._runner.cleanup()

    async def _handle(self, request: web.Request) -> web.Response:
        healthy = all(self.status.values())
        return web.json_response({"healthy": healthy, "components": self.status}, status=200 if healthy else 503)
