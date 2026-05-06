"""Async Jito bundle client using persistent HTTP/2 connections."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from infrastructure.jito.tip_optimizer import calculate_tip_lamports

LOGGER = structlog.get_logger(__name__)


class JitoBundleClient:
    """Submits signed transaction bundles to the Jito block engine."""

    def __init__(self, relayer_url: str, auth_key: str, tip_account: str, base_tip_lamports: int, max_tip_percentage: float) -> None:
        self._url = relayer_url.rstrip("/")
        self._tip_account = tip_account
        self._base_tip = base_tip_lamports
        self._max_tip_percentage = max_tip_percentage
        self._client = httpx.AsyncClient(http2=True, timeout=2.0, headers={"x-jito-auth": auth_key} if auth_key else {})

    async def submit_bundle(self, signed_transactions: list[str], opportunity: dict[str, Any], target_slot: int | None = None) -> str:
        """Fire-and-forget submit a Jito bundle and return its bundle id."""
        tip = calculate_tip_lamports(
            float(opportunity.get("confidence", 0.0)),
            float(opportunity.get("network_congestion", 0.0)),
            float(opportunity.get("urgency_ms", 0.0)),
            int(opportunity.get("expected_profit_lamports", 0) or 0),
            self._base_tip,
            self._max_tip_percentage,
        )
        params: dict[str, Any] = {"transactions": signed_transactions, "tip_account": self._tip_account, "tip_lamports": tip}
        if target_slot is not None:
            params["target_slot"] = target_slot
        payload = {"jsonrpc": "2.0", "id": 1, "method": "sendBundle", "params": [params]}
        response = await self._client.post(f"{self._url}/api/v1/bundles", json=payload)
        response.raise_for_status()
        result = response.json().get("result", {})
        bundle_id = str(result.get("bundle_id", result))
        LOGGER.info("jito_bundle_submitted", bundle_id=bundle_id, tip_lamports=tip)
        return bundle_id

    async def close(self) -> None:
        """Close persistent relayer connection."""
        await self._client.aclose()
