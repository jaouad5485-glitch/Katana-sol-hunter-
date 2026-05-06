# Solo-Hunter Ultra

Solo-Hunter Ultra is a production-oriented Solana HFT sniper bot foundation focused on low-latency event handling, early filter rejection, warm blockhash access, Redis binary caching, and Jito bundle submission.

> Phase 1 foundation is implemented. Real-money trading requires private RPC/Jito credentials, wallet provisioning, model validation, and exchange-specific transaction templates before production use.

## Features Implemented

- `uvloop` application entrypoint.
- Async event bus with wildcard subscriptions and bounded queues.
- Engine lifecycle state machine: `INITIALIZING`, `WARMING_UP`, `ACTIVE`, `DEGRADED`, `SHUTDOWN`.
- Ordered dependency initialization and graceful shutdown hooks.
- Circuit breaker primitives.
- HTTP/2 RPC pool with health checks, latency tracking, failover, and keep-alive.
- Redis binary cache using `decode_responses=False` and msgpack.
- Aggressive blockhash cache with 2-second refresh and Redis sharing.
- Auto-reconnecting WebSocket manager for Raydium, Orca Whirlpool, Pump.fun, and block subscriptions.
- Jito bundle client with adaptive tip calculation.
- Cascading filter layers and ONNX predictor fallback.
- SQLite schema and repository skeleton.
- Prometheus metrics and `/health` endpoint.
- Docker Compose stack with Redis and app services.

## Setup

```bash
cd solo-hunter-ultra
cp config/.env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

Edit `.env` with private RPC, WebSocket, Jito, and wallet encryption values. Never commit `.env`, wallet files, or database files.

## Run Locally

```bash
python main.py
```

## Run with Docker

```bash
docker compose up --build
```

## Benchmark

```bash
python scripts/benchmark.py
```

The benchmark exercises the in-process strategy evaluation pipeline. Live end-to-end latency depends on RPC/Jito placement, private networking, validator proximity, and wallet signing implementation.

## Security Notes

- Secrets are loaded from `.env`/environment-expanded YAML only.
- `.env`, `keys/`, and `data/` are gitignored.
- Wallet payloads are encrypted with AES-256-GCM in `wallet/key_manager.py`.
- Structured logging avoids wallet secret material.

## Phase Roadmap

1. Foundation: config, event bus, RPC pool, WebSocket manager, logging.
2. Core execution: Raydium templates, Jito bundles, retries, database writes.
3. Intelligence: ONNX model, wallet profiling, advanced filters.
4. Operations: metrics, health checks, fail-safes, integration tests.
5. Optimization: hot-path profiling, load testing, and colocated deployment.
