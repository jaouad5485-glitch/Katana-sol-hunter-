"""Solo-Hunter Ultra event-driven async engine."""

from __future__ import annotations

import asyncio
import gc
from pathlib import Path
from typing import Any

import structlog
import yaml
from dotenv import load_dotenv

from core.event_bus import AsyncEventBus, Event
from core.lifecycle import CircuitBreaker, EngineState
from execution.fail_safes import FailSafeConfig, FailSafes
from infrastructure.jito.bundle_client import JitoBundleClient
from infrastructure.redis.cache import RedisCache
from infrastructure.rpc.blockhash_cache import BlockhashCache
from infrastructure.rpc.connection_pool import RpcConnectionPool
from infrastructure.websocket.manager import WebSocketManager
from intelligence.feature_engine import FeatureEngine
from intelligence.predictor import OnnxPredictor
from monitoring.health import HealthServer
from monitoring.metrics import OPPORTUNITIES_SEEN_TOTAL, start_metrics_server
from strategy.htf_sniper import HtfSniperStrategy

LOGGER = structlog.get_logger(__name__)


class SoloHunterEngine:
    """Coordinates lifecycle, dependencies, strategies, and graceful shutdown."""

    def __init__(self, settings_path: str = "config/settings.yaml") -> None:
        load_dotenv()
        self.settings = self._load_settings(settings_path)
        self.state = EngineState.INITIALIZING
        self.event_bus = AsyncEventBus()
        self.breakers = {
            "rpc": CircuitBreaker("rpc"),
            "jito": CircuitBreaker("jito"),
            "execution": CircuitBreaker("execution"),
        }
        self.redis: RedisCache | None = None
        self.rpc_pool: RpcConnectionPool | None = None
        self.blockhash_cache: BlockhashCache | None = None
        self.websocket: WebSocketManager | None = None
        self.jito: JitoBundleClient | None = None
        self.strategy: HtfSniperStrategy | None = None
        self.health = HealthServer()
        self.fail_safes = FailSafes(FailSafeConfig(
            max_daily_loss_sol=float(self.settings["bot"]["max_daily_loss_sol"]),
            max_open_positions=int(self.settings["bot"]["max_open_positions"]),
        ))
        self._accepting_opportunities = True

    async def start(self) -> None:
        """Ordered initialization: metrics, Redis, RPC, blockhash, WebSocket, Jito, bus, strategies, execution, intelligence, health."""
        structlog.configure(processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.processors.JSONRenderer()])
        start_metrics_server(int(self.settings["monitoring"]["prometheus_port"]))
        redis_cfg = self.settings["redis"]
        self.redis = RedisCache(redis_cfg["host"], int(redis_cfg["port"]), int(redis_cfg["db"]))
        await self.redis.ping()
        rpc_cfg = self.settings["rpc"]
        self.rpc_pool = RpcConnectionPool(rpc_cfg["endpoints"], float(rpc_cfg["timeout"]), int(rpc_cfg["max_connections"]))
        await self.rpc_pool.start()
        self.blockhash_cache = BlockhashCache(self.rpc_pool, self.redis)
        await self.blockhash_cache.start()
        self.websocket = WebSocketManager(self.settings["websocket"]["endpoints"], self.event_bus, float(self.settings["websocket"]["reconnect_interval"]), int(self.settings["websocket"]["max_reconnect_attempts"]))
        jito_cfg = self.settings["jito"]
        self.jito = JitoBundleClient(jito_cfg["relayer_url"], jito_cfg["auth_key"], jito_cfg["tip_account"], int(jito_cfg["base_tip_lamports"]), float(jito_cfg["max_tip_percentage"]))
        await self.event_bus.start()
        predictor = OnnxPredictor()
        await predictor.start()
        self.strategy = HtfSniperStrategy(FeatureEngine(), predictor, float(self.settings["filters"]["min_confidence_score"]))
        self.event_bus.subscribe("token.listing.new", self._on_listing)
        self.event_bus.subscribe("system.shutdown", self._on_shutdown)
        self.event_bus.subscribe("error.critical", self._on_critical)
        self.state = EngineState.WARMING_UP
        gc.disable()
        await self.websocket.start()
        await self.health.start()
        self.state = EngineState.ACTIVE
        LOGGER.info("engine_started", state=self.state)

    async def stop(self) -> None:
        """Gracefully stop accepting opportunities, close positions, and cleanup connections."""
        self.state = EngineState.SHUTDOWN
        self._accepting_opportunities = False
        await self.fail_safes.emergency_close_all()
        if self.websocket:
            await self.websocket.stop()
        if self.blockhash_cache:
            await self.blockhash_cache.stop()
        if self.rpc_pool:
            await self.rpc_pool.stop()
        if self.jito:
            await self.jito.close()
        await self.event_bus.stop()
        if self.redis:
            await self.redis.close()
        await self.health.stop()
        gc.enable()
        LOGGER.info("engine_stopped")

    async def _on_listing(self, event: Event) -> None:
        OPPORTUNITIES_SEEN_TOTAL.inc()
        if not self._accepting_opportunities or not self.strategy:
            return
        candidate = await self.strategy.evaluate(event.payload)
        if candidate:
            await self.event_bus.publish("opportunity.confirmed", candidate)

    async def _on_shutdown(self, event: Event) -> None:
        await self.stop()

    async def _on_critical(self, event: Event) -> None:
        self.state = EngineState.DEGRADED
        LOGGER.error("critical_error", **event.payload)

    def _load_settings(self, path: str) -> dict[str, Any]:
        text = Path(path).read_text()
        import os
        for key, value in os.environ.items():
            text = text.replace("${" + key + "}", value)
        return yaml.safe_load(text)
