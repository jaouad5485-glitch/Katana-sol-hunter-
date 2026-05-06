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

## Phase 2 Rust Execution Engine

Phase 2 adds a Rust Cargo workspace under `rust/` for the standalone hot-path binary `hunterd`. The Python service remains the control plane for monitoring, retraining, and analytics, while Rust owns shred ingestion, synchronous filtering, transaction assembly, signing, and bundle submission.

Workspace crates:

- `sh_sniffer`: UDP Shredstream ingestion, program-id prefiltering, shred assembly hooks, and signal extraction for Raydium AMM, Raydium CPMM, Orca Whirlpool, and Pump.fun.
- `filter_stack`: synchronous cascading filters on bounded channels.
- `tx_builder`: pre-templated deterministic VersionedTransaction-like swap drafts with compute budget and Jito tip instructions.
- `execution`: pinned execution thread for build/sign/simulate/submit flow.
- `rpc_pool`, `state_cache`, `wallet`, `intelligence`, and `metrics`: support crates for RPC, hot cache, key loading/signing, scoring, and Prometheus text metrics.
- `hunterd`: main binary that validates required environment variables and starts the hot-path pipeline.

Required environment variables for `hunterd`:

```bash
WALLET_ENCRYPTION_KEY=...
JITO_AUTH_KEY=...
HELIUS_RPC_URL=https://...
SHREDSTREAM_BIND_ADDR=0.0.0.0:20000
```

Build and test:

```bash
cd rust
cargo test --workspace
cargo build --release -p hunterd
./scripts/bench_latency.sh
```

> Note: this Phase 2 workspace is intentionally dependency-light in this repository so it compiles in network-restricted CI. Production hardening should replace the std-only compatibility shims with the requested crates (`socket2`, `crossbeam-channel`, `reqwest`, `hyper`, `secrecy`, `argon2`, `aes-gcm`, `ort`, Redis msgpack integration, and real Solana `VersionedTransaction` types) before mainnet funds are connected.
