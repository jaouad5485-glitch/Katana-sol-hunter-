# Solo-Hunter Ultra — Production Deployment Guide

> **Version**: Production-Ready Release  
> **Last Updated**: 2026-05-13  
> **Status**: Ready for production deployment with real capital

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Security Configuration](#security-configuration)
4. [Environment Setup](#environment-setup)
5. [Deployment Options](#deployment-options)
6. [Operational Procedures](#operational-procedures)
7. [Monitoring and Alerts](#monitoring-and-alerts)
8. [Emergency Procedures](#emergency-procedures)
9. [Troubleshooting](#troubleshooting)

---

## Overview

Solo-Hunter Ultra is a production-oriented Solana HFT sniper bot designed for low-latency trading of new token listings. This guide covers deployment in production environments with real capital.

### Architecture Highlights

- **Event-driven async** using uvloop for maximum performance
- **Multi-layer security** with AES-256-GCM wallet encryption
- **Circuit breakers** for graceful degradation under failure
- **Jito bundle support** for accelerated transaction inclusion
- **Kelly-based position sizing** for optimal capital allocation
- **Emergency fail-safes** with market sell capability

### Production Readiness Checklist

- [x] Emergency close implementation (Jupiter-powered market sells)
- [x] HTTPS enforcement for all RPC endpoints
- [x] Circuit breaker with automatic recovery
- [x] Position tracking and PnL monitoring
- [x] Comprehensive test suite (pytest)
- [x] Prometheus metrics and health endpoints
- [x] Structured logging (JSON format)

---

## Prerequisites

### Required Infrastructure

| Component | Specification | Purpose |
|-----------|---------------|---------|
| Python | 3.11+ | Runtime environment |
| Redis | 7.0+ | Binary cache, blockhash sharing |
| Private RPC | Helius/QuickNode | Low-latency blockchain access |
| Jito Access | Block engine API | Bundle submission |
| Wallet | Encrypted Solana key | Trading authority |

### Security Requirements

- Git should be configured with SSH or HTTPS credentials
- `.env` file must contain all required secrets
- Wallet encryption key must be 32+ characters
- All RPC endpoints must use HTTPS

---

## Security Configuration

### 1. Generate Wallet Encryption Key

Generate a secure 32+ character encryption key:

```bash
openssl rand -base64 32
```

Store this securely — it encrypts your wallet at rest.

### 2. Encrypt Your Wallet

```python
from key_manager import KeyManager
import json

# Load your base58 private key
wallet_data = {
    "private_key": "your_base58_private_key_here",
    "public_key": "your_solana_address_here"
}

key_manager = KeyManager(
    key_path="./keys/encrypted_wallet.json",
    encryption_key="your_32_character_encryption_key_here"
)
key_manager.encrypt_and_store(wallet_data)
```

### 3. Environment Variables

Create `.env` file with all required variables:

```bash
# RPC Endpoints (HTTPS Required)
HELIUS_RPC_URL=https://mainnet.helius-rpc.com/?api-key=YOUR_KEY
QUICKNODE_RPC_URL=https://solana-mainnet.quiknode.pro/YOUR_KEY

# WebSocket
HELIUS_WS_URL=wss://mainnet.helius-rpc.com/?api-key=YOUR_KEY

# Jito Configuration
JITO_RELAYER_URL=https://mainnet.block-engine.jito.wtf
JITO_AUTH_KEY=your_jito_auth_key
JITO_TIP_ACCOUNT=96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5

# Wallet Encryption
WALLET_ENCRYPTION_KEY=your_32_character_encryption_key_here

# Redis
REDIS_URL=redis://localhost:6379/
```

### 4. Security Validation

The system automatically validates:

- HTTPS enforcement on all RPC endpoints
- Required environment variables are present
- Wallet file exists and is readable
- Jito authentication is configured

---

## Environment Setup

### Option 1: Virtual Environment

```bash
cd solo-hunter-ultra

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest

# Start bot
python main.py
```

### Option 2: Docker Deployment

```bash
# Build and start
docker compose up --build

# View logs
docker compose logs -f app

# Stop gracefully
docker compose down
```

### Option 3: Kubernetes

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: solo-hunter-ultra
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: app
        image: your-registry/solo-hunter-ultra:latest
        env:
        - name: HELIUS_RPC_URL
          valueFrom:
            secretKeyRef:
              name: bot-secrets
              key: helius-rpc-url
        ports:
        - containerPort: 9090
```

---

## Operational Procedures

### Starting the Bot

```bash
# Activate environment
source .venv/bin/activate

# Start with logging
python main.py 2>&1 | tee logs/bot-$(date +%Y%m%d-%H%M%S).log

# Or start in background
nohup python main.py > bot.log 2>&1 &
```

### Monitoring Status

```bash
# Check health endpoint
curl http://localhost:9090/health

# View Prometheus metrics
curl http://localhost:9090/metrics

# Check Redis connectivity
redis-cli ping
```

### Stopping the Bot

```bash
# Graceful shutdown (SIGTERM)
pkill -f "python main.py"

# Emergency stop (SIGINT)
pkill -INT -f "python main.py"
```

### Log Analysis

```bash
# View recent errors
grep -i error logs/bot-*.log | tail -50

# View trading activity
grep -i "opportunity" logs/bot-*.log | tail -20

# View circuit breaker events
grep -i "breaker" logs/bot-*.log | tail -20
```

---

## Monitoring and Alerts

### Prometheus Metrics

Key metrics to monitor:

| Metric | Description | Alert Threshold |
|--------|-------------|----------------|
| `opportunities_seen_total` | New token opportunities detected | > 100/hour |
| `rpc_latency_ms` | RPC response time | > 500ms avg |
| `circuit_breaker_state` | Circuit breaker status | != closed |
| `daily_pnl_sol` | Daily profit/loss | < -1.0 SOL |
| `open_positions` | Current position count | > 10 |
| `emergency_active` | Emergency close in progress | = true |

### Setting Up Alerts

```yaml
# prometheus_alerts.yml
groups:
- name: solo-hunter-alerts
  rules:
  - alert: HighRpcLatency
    expr: avg(rpc_latency_ms) > 500
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "RPC latency exceeds 500ms"

  - alert: DailyLossLimit
    expr: daily_pnl_sol < -1.0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "Daily loss limit reached"

  - alert: CircuitBreakerOpen
    expr: circuit_breaker_state != 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "Circuit breaker is open"
```

### Health Check Endpoint

```bash
# Detailed health check
curl -s http://localhost:9090/health | jq .
```

---

## Emergency Procedures

### Emergency Stop

If you need to stop trading immediately:

```bash
# Send emergency shutdown signal
curl -X POST http://localhost:9090/shutdown
```

This triggers:
1. Trading is immediately halted
2. All open positions are closed via market sells
3. Jito bundles are submitted for fastest execution
4. System enters graceful shutdown

### Manual Position Close

```python
from execution.fail_safes import FailSafes, FailSafeConfig

config = FailSafeConfig(
    max_daily_loss_sol=1.0,
    max_open_positions=10,
)

fail_safes = FailSafes(config)

# Emergency close all positions
results = await fail_safes.emergency_close_all()
```

### Circuit Breaker Recovery

If a circuit breaker is open:

```bash
# Check circuit breaker status
curl http://localhost:9090/health | jq '.circuit_breakers'

# Wait for automatic recovery (60 seconds)
# Or restart the bot
pkill -f "python main.py"
python main.py
```

---

## Troubleshooting

### Common Issues

#### Redis Connection Failed

```bash
# Check Redis is running
redis-cli ping

# Restart Redis
sudo systemctl restart redis-server

# Verify connection
redis-cli -h localhost -p 6379 ping
```

#### RPC Endpoint Unhealthy

```bash
# Check endpoint health
curl -X POST https://your-rpc.com -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"getHealth"}'

# Switch to backup endpoint in config
# Edit config/settings.yaml
```

#### Wallet Decryption Failed

```bash
# Verify encryption key
echo $WALLET_ENCRYPTION_KEY

# Re-encrypt wallet if needed
python scripts/encrypt_wallet.py

# Check wallet file permissions
ls -la keys/encrypted_wallet.json
```

#### Jito Bundle Submission Failed

```bash
# Check Jito status
curl https://mainnet.block-engine.jito.wtf/api/v1/status

# Verify authentication
curl -H "Authorization: Bearer $JITO_AUTH_KEY" \
  https://mainnet.block-engine.jito.wtf/api/v1/status
```

### Debug Mode

Enable debug logging:

```bash
# Set log level
export LOG_LEVEL=DEBUG

# Run with verbose output
python main.py --log-level DEBUG
```

### Performance Profiling

```bash
# Run benchmark
python scripts/benchmark.py

# Profile memory usage
python -m memory_profiler main.py

# Profile CPU usage
py-spy top -- python main.py
```

---

## Production Checklist

Before deploying with real capital:

- [ ] All environment variables configured
- [ ] Wallet encrypted and tested
- [ ] Redis connection verified
- [ ] RPC endpoints responding
- [ ] Jito authentication working
- [ ] Health endpoint responding
- [ ] Prometheus metrics accessible
- [ ] Alerts configured
- [ ] Runbook documented
- [ ] Emergency contacts established
- [ ] Test trades executed (small amounts)

---

## Support and Resources

- **GitHub Issues**: Report bugs and feature requests
- **Documentation**: See inline code comments and docstrings
- **Discord**: Join community for real-time support

---

## Security Reminders

1. **Never commit `.env` or wallet files to version control**
2. **Rotate encryption keys regularly**
3. **Monitor for unauthorized access**
4. **Test emergency procedures before going live**
5. **Start with small capital and increase gradually**

---

*Good luck with your trading! Trade safe.*