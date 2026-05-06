# Solo-Hunter Ultra Phase 2 Rust Hot Path

This branch is intentionally scoped to Phase 2 only so it can merge cleanly after the Phase 1 Python control-plane branch has landed. The Rust workspace lives under `rust/` and adds the standalone `hunterd` execution-engine skeleton plus independently testable support crates.

## Build and test

```bash
cd solo-hunter-ultra/rust
cargo test --workspace --locked
cargo build --release -p hunterd
./scripts/bench_latency.sh
```

## Required runtime environment

```bash
WALLET_ENCRYPTION_KEY=...
JITO_AUTH_KEY=...
HELIUS_RPC_URL=https://...
SHREDSTREAM_BIND_ADDR=0.0.0.0:20000
```

The current implementation is dependency-light so it can compile in network-restricted CI. Before real mainnet trading, replace the compatibility shims with the production integrations documented in the crate comments: `socket2`, `crossbeam-channel`, `reqwest`/HTTP2, real Solana `VersionedTransaction` types, AES-256-GCM + Argon2id wallet decryption, Redis msgpack cache, ONNX Runtime, and Jito bundle status tracking.
