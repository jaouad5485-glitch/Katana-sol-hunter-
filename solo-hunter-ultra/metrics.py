"""Prometheus metrics for trading and infrastructure latency."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, start_http_server

OPPORTUNITY_EVAL_MS = Histogram("opportunity_eval_ms", "Opportunity evaluation latency in milliseconds")
EXECUTION_TOTAL_MS = Histogram("execution_total_ms", "Signal to submission latency in milliseconds")
OPPORTUNITIES_SEEN_TOTAL = Counter("opportunities_seen_total", "Total opportunities detected")
OPPORTUNITIES_FILTERED_TOTAL = Counter(
    "opportunities_filtered_total", "Filtered opportunities", ["layer", "reason"]
)
TRADES_EXECUTED_TOTAL = Counter("trades_executed_total", "Trades executed", ["dex", "result"])
OPEN_POSITIONS = Gauge("open_positions", "Open position count")
SOL_BALANCE = Gauge("sol_balance", "SOL balance")
PNL_TODAY_SOL = Gauge("pnl_today_sol", "Daily PnL in SOL")
RPC_LATENCY_MS = Gauge("rpc_latency_ms", "RPC endpoint latency", ["endpoint"])
JITO_BUNDLE_SUCCESS_RATE = Gauge("jito_bundle_success_rate", "Jito bundle success rate")


def start_metrics_server(port: int) -> None:
    """Start Prometheus HTTP exporter."""
    start_http_server(port)
