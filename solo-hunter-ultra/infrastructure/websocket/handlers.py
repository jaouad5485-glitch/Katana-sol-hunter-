"""WebSocket log parsing utilities."""

from __future__ import annotations

import json
from typing import Any

RAYDIUM_AMM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
ORCA_WHIRLPOOL = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
PUMP_FUN = "6EF8rrecthR5Dkprh14b3k7x1hhtQzuivzWVwB5Kpump"
SUPPORTED_PROGRAMS = {RAYDIUM_AMM: "raydium", ORCA_WHIRLPOOL: "orca", PUMP_FUN: "pump_fun"}


def parse_program_log(raw_message: bytes | str) -> dict[str, Any] | None:
    """Parse a Solana logs notification into a normalized opportunity payload."""
    message = json.loads(raw_message)
    params = message.get("params", {})
    result = params.get("result", {})
    value = result.get("value", {})
    logs = value.get("logs", [])
    joined = " ".join(logs).lower()
    if not any(marker in joined for marker in ("initialize", "pool", "mint", "buy")):
        return None
    signature = value.get("signature", "")
    program = _detect_program(joined)
    if program is None:
        return None
    return {
        "token_mint": _extract_after(logs, "mint") or "11111111111111111111111111111111",
        "pool_address": _extract_after(logs, "pool") or signature,
        "dex": program,
        "liquidity_usd": 0.0,
        "dev_wallet": _extract_after(logs, "owner") or "",
        "signature": signature,
    }


def _detect_program(text: str) -> str | None:
    for program_id, dex in SUPPORTED_PROGRAMS.items():
        if program_id.lower() in text or dex in text:
            return dex
    return None


def _extract_after(logs: list[str], marker: str) -> str | None:
    for log in logs:
        parts = log.replace(":", " ").split()
        lowered = [part.lower() for part in parts]
        if marker in lowered:
            idx = lowered.index(marker)
            if idx + 1 < len(parts):
                return parts[idx + 1]
    return None
