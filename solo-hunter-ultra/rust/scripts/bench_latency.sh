#!/usr/bin/env bash
set -euo pipefail
cargo run --release -p hunterd --example latency_bench
