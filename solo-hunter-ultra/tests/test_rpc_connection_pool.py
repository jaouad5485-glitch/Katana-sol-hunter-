"""Tests for RPC connection pool and failover logic."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from time import monotonic

import pytest

from infrastructure.rpc.connection_pool import (
    RpcConnectionPool,
    RpcEndpoint,
    _validate_https,
    SecurityError,
)


class TestRpcEndpoint:
    """Tests for RpcEndpoint dataclass."""

    def test_default_values(self) -> None:
        """Test default endpoint values."""
        endpoint = RpcEndpoint(url="https://api.mainnet-beta.solana.com")
        assert endpoint.url == "https://api.mainnet-beta.solana.com"
        assert endpoint.weight == 1.0
        assert endpoint.priority == 1
        assert endpoint.healthy is True
        assert endpoint.latency_ms == 1_000.0
        assert endpoint.failures == 0
        assert endpoint.last_checked > 0

    def test_custom_values(self) -> None:
        """Test custom endpoint values."""
        endpoint = RpcEndpoint(
            url="https://custom-rpc.example.com",
            weight=2.0,
            priority=3,
            healthy=False,
            latency_ms=150.5,
            failures=5,
            last_checked=12345.0,
        )
        assert endpoint.url == "https://custom-rpc.example.com"
        assert endpoint.weight == 2.0
        assert endpoint.priority == 3
        assert endpoint.healthy is False
        assert endpoint.latency_ms == 150.5
        assert endpoint.failures == 5
        assert endpoint.last_checked == 12345.0


class TestValidateHttps:
    """Tests for HTTPS validation function."""

    def test_valid_https_url(self) -> None:
        """Test validation of valid HTTPS URL."""
        url = "https://api.mainnet-beta.solana.com"
        result = _validate_https(url)
        assert result == url

    def test_http_url_rejected(self) -> None:
        """Test that HTTP URLs are rejected."""
        with pytest.raises(SecurityError) as exc_info:
            _validate_https("http://api.mainnet-beta.solana.com")
        assert "must use HTTPS" in str(exc_info.value)

    def test_invalid_scheme_rejected(self) -> None:
        """Test that non-HTTP schemes are rejected."""
        with pytest.raises(SecurityError):
            _validate_https("ftp://example.com")
        with pytest.raises(SecurityError):
            _validate_https("socket://example.com")


class TestRpcConnectionPool:
    """Tests for RpcConnectionPool class."""

    @pytest.fixture
    def endpoints(self) -> list[dict[str, any]]:
        """Create test endpoint configuration."""
        return [
            {"url": "https://primary.example.com", "weight": 1.0, "priority": 1},
            {"url": "https://secondary.example.com", "weight": 0.5, "priority": 2},
        ]

    @pytest.fixture
    def pool(self, endpoints: list[dict[str, any]]) -> RpcConnectionPool:
        """Create RPC connection pool for testing."""
        return RpcConnectionPool(endpoints=endpoints, timeout=2.0, max_connections=10)

    def test_initialization(self, pool: RpcConnectionPool) -> None:
        """Test pool initialization with endpoints."""
        assert len(pool.endpoints) == 2
        assert pool._rr_index == 0
        assert pool._running is False
        assert pool._health_task is None

    def test_https_enforcement_default(self, endpoints: list[dict[str, any]]) -> None:
        """Test that HTTPS is enforced by default."""
        with pytest.raises(SecurityError):
            RpcConnectionPool(
                endpoints=[{"url": "http://insecure.example.com"}],
                enforce_https=True,
            )

    def test_https_bypass_option(self, endpoints: list[dict[str, any]]) -> None:
        """Test that HTTPS can be disabled."""
        pool = RpcConnectionPool(
            endpoints=[{"url": "http://insecure.example.com"}],
            enforce_https=False,
        )
        assert len(pool.endpoints) == 1
        assert pool.endpoints[0].url == "http://insecure.example.com"

    @pytest.mark.asyncio
    async def test_start_starts_health_check(self, pool: RpcConnectionPool) -> None:
        """Test that start initiates health checking."""
        await pool.start()
        assert pool._running is True
        assert pool._health_task is not None
        await pool.stop()

    @pytest.mark.asyncio
    async def test_stop_stops_health_check(self, pool: RpcConnectionPool) -> None:
        """Test that stop terminates health checking."""
        await pool.start()
        assert pool._running is True
        await pool.stop()
        assert pool._running is False

    @pytest.mark.asyncio
    async def test_call_selects_endpoint(self, pool: RpcConnectionPool) -> None:
        """Test that call selects an endpoint."""
        mock_response = {"jsonrpc": "2.0", "id": 1, "result": "success"}
        with patch.object(pool._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(
                raise_for_status=MagicMock(),
                json=MagicMock(return_value=mock_response),
            )
            result = await pool.call("getHealth")
            assert result == "success"
            assert pool._rr_index == 1

    @pytest.mark.asyncio
    async def test_call_handles_rpc_error(self, pool: RpcConnectionPool) -> None:
        """Test error handling for RPC responses."""
        error_response = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32600, "message": "Invalid Request"}}
        with patch.object(pool._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(
                raise_for_status=MagicMock(),
                json=MagicMock(return_value=error_response),
            )
            with pytest.raises(RuntimeError) as exc_info:
                await pool.call("getHealth")
            assert "-32600" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_call_tracks_failures(self, pool: RpcConnectionPool) -> None:
        """Test that failed calls increment failure counter."""
        with patch.object(pool._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = Exception("Connection refused")
            try:
                await pool.call("getHealth")
            except Exception:
                pass
        endpoint = pool.endpoints[0]
        assert endpoint.failures >= 1

    def test_select_endpoint_prefers_healthy(self, pool: RpcConnectionPool) -> None:
        """Test endpoint selection prefers healthy endpoints."""
        pool.endpoints[0].healthy = True
        pool.endpoints[1].healthy = True
        selected = pool._select_endpoint()
        assert selected.healthy is True

    def test_select_endpoint_skips_unhealthy(self, pool: RpcConnectionPool) -> None:
        """Test endpoint selection skips unhealthy endpoints."""
        pool.endpoints[0].healthy = False
        pool.endpoints[0].failures = 5
        pool.endpoints[1].healthy = True
        selected = pool._select_endpoint()
        assert selected.url == pool.endpoints[1].url

    def test_select_endpoint_fails_all_unhealthy(self, pool: RpcConnectionPool) -> None:
        """Test that selection fails when all endpoints unhealthy."""
        pool.endpoints[0].healthy = False
        pool.endpoints[0].failures = 5
        pool.endpoints[1].healthy = False
        pool.endpoints[1].failures = 5
        with pytest.raises(RuntimeError) as exc_info:
            pool._select_endpoint()
        assert "no healthy RPC endpoints" in str(exc_info.value)

    def test_select_endpoint_uses_priority(self, pool: RpcConnectionPool) -> None:
        """Test endpoint selection respects priority."""
        pool.endpoints[0].healthy = True
        pool.endpoints[0].priority = 1
        pool.endpoints[0].latency_ms = 100.0
        pool.endpoints[1].healthy = True
        pool.endpoints[1].priority = 2
        pool.endpoints[1].latency_ms = 50.0
        selected = pool._select_endpoint()
        assert selected.priority == 1

    def test_select_endpoint_round_robin(self, pool: RpcConnectionPool) -> None:
        """Test round-robin selection among equal priority endpoints."""
        for endpoint in pool.endpoints:
            endpoint.healthy = True
            endpoint.priority = 1
            endpoint.latency_ms = 100.0
        first = pool._select_endpoint()
        pool._rr_index = 0
        second = pool._select_endpoint()
        assert first.url != second.url

    @pytest.mark.asyncio
    async def test_health_loop_checks_all_endpoints(self, pool: RpcConnectionPool) -> None:
        """Test that health loop checks all configured endpoints."""
        await pool.start()
        await asyncio.sleep(0.1)
        for endpoint in pool.endpoints:
            assert endpoint.last_checked > 0
        await pool.stop()

    @pytest.mark.asyncio
    async def test_endpoint_recovery(self, pool: RpcConnectionPool) -> None:
        """Test endpoint recovery after failures."""
        endpoint = pool.endpoints[0]
        endpoint.healthy = False
        endpoint.failures = 2
        with patch.object(pool._client, "post", new_callable=AsyncMock) as mock_post:
            mock_response = {"jsonrpc": "2.0", "id": 1, "result": "ok"}
            mock_post.return_value = MagicMock(
                raise_for_status=MagicMock(),
                json=MagicMock(return_value=mock_response),
            )
            await pool._check_endpoint(endpoint)
        assert endpoint.healthy is True
        assert endpoint.failures == 0

    @pytest.mark.asyncio
    async def test_health_check_updates_latency(self, pool: RpcConnectionPool) -> None:
        """Test that health check updates latency metrics."""
        endpoint = pool.endpoints[0]
        initial_latency = endpoint.latency_ms
        with patch.object(pool._client, "post", new_callable=AsyncMock) as mock_post:
            mock_response = {"jsonrpc": "2.0", "id": 1, "result": "ok"}
            mock_post.return_value = MagicMock(
                raise_for_status=MagicMock(),
                json=MagicMock(return_value=mock_response),
            )
            await pool._check_endpoint(endpoint)
        assert endpoint.latency_ms != initial_latency

    @pytest.mark.asyncio
    async def test_concurrent_calls(self, pool: RpcConnectionPool) -> None:
        """Test concurrent RPC calls."""
        mock_response = {"jsonrpc": "2.0", "id": 1, "result": "success"}
        call_count = 0
        
        async def mock_post(url, json):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return MagicMock(
                raise_for_status=MagicMock(),
                json=MagicMock(return_value=mock_response),
            )
        
        with patch.object(pool._client, "post", side_effect=mock_post):
            results = await asyncio.gather(
                pool.call("getHealth"),
                pool.call("getSlot"),
                pool.call("getBlockHeight"),
            )
        assert len(results) == 3
        assert all(r == "success" for r in results)
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self, pool: RpcConnectionPool) -> None:
        """Test graceful shutdown of connection pool."""
        await pool.start()
        await pool.stop()
        assert pool._running is False
        assert pool._health_task is None or pool._health_task.done()