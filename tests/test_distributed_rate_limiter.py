import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient

from rate_limiter import DistributedRateLimiter, InMemoryFallbackLimiter
import app


class TestDistributedRateLimiter(unittest.IsolatedAsyncioTestCase):
    """Unit and integration tests for Distributed Redis Rate Limiter with Fail-Open strategy."""

    async def test_in_memory_fallback_sliding_window(self):
        """In-memory fallback limiter correctly limits at 30 req/minute."""
        limiter = InMemoryFallbackLimiter(requests_limit=3, window_seconds=60)
        self.assertTrue(limiter.is_allowed("ip:127.0.0.1"))
        self.assertTrue(limiter.is_allowed("ip:127.0.0.1"))
        self.assertTrue(limiter.is_allowed("ip:127.0.0.1"))
        # 4th request exceeds limit
        self.assertFalse(limiter.is_allowed("ip:127.0.0.1"))
        # Different IP is not blocked
        self.assertTrue(limiter.is_allowed("ip:192.168.1.1"))

    async def test_fail_open_when_redis_unreachable_on_startup(self):
        """When Redis is unreachable on startup, fails open if strict=False."""
        limiter = DistributedRateLimiter(redis_url="redis://nonexistent-host:6379/0", strict=False)
        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_client = AsyncMock()
            mock_client.ping.side_effect = Exception("Connection refused to Redis")
            mock_from_url.return_value = mock_client

            initialized = await limiter.init()
            self.assertFalse(initialized)
            self.assertFalse(limiter.is_redis_available())

    async def test_fail_closed_when_strict_is_true(self):
        """When Redis is unreachable on startup, raises exception if strict=True."""
        limiter = DistributedRateLimiter(redis_url="redis://nonexistent-host:6379/0", strict=True)
        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_client = AsyncMock()
            mock_client.ping.side_effect = ConnectionError("Strict Redis connection failed")
            mock_from_url.return_value = mock_client

            with self.assertRaises(ConnectionError):
                await limiter.init()

    async def test_redis_runtime_failure_fails_open(self):
        """When Redis crashes during a check, limiter logs critical error and allows request."""
        limiter = DistributedRateLimiter(strict=False)
        limiter._redis_available = True
        mock_redis = AsyncMock()
        mock_redis.evalsha.side_effect = Exception("Redis cluster timeout")
        limiter.redis_client = mock_redis
        limiter._lua_sha = "mock_sha"

        req = MagicMock()
        req.headers = {"x-forwarded-for": "10.0.0.1"}
        req.url.path = "/api/chat"
        req.client.host = "10.0.0.1"

        # Should NOT raise 503; fails open to fallback limiter
        allowed = await limiter.check(req, limit=30, window_seconds=60)
        self.assertTrue(allowed)

    async def test_redis_exceeded_raises_429(self):
        """When Redis reports limit exceeded (PTTL > 0), raises 429."""
        limiter = DistributedRateLimiter(strict=False)
        limiter._redis_available = True
        mock_redis = AsyncMock()
        mock_redis.evalsha.return_value = 45000  # 45 seconds remaining
        limiter.redis_client = mock_redis
        limiter._lua_sha = "mock_sha"

        req = MagicMock()
        req.headers = {"x-forwarded-for": "10.0.0.1"}
        req.url.path = "/api/chat"
        req.client.host = "10.0.0.1"

        with self.assertRaises(HTTPException) as ctx:
            await limiter.check(req, limit=30, window_seconds=60)

        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("30 requests/minute", ctx.exception.detail)


class TestRateLimiterEndpointIntegration(unittest.TestCase):
    """Tests rate limiter integration on the live FastAPI app."""

    def setUp(self):
        self.client = TestClient(app.app)
        app.rate_limiter.fallback_limiter.reset()

    def test_31_requests_returns_429(self):
        """Acceptance Criteria: Hitting the endpoint 31 times in a minute returns a 429 Too Many Requests HTTP status."""
        # 30 requests should fail with 400 (empty message validation)
        for i in range(30):
            resp = self.client.post(
                "/api/chat",
                data={"message": ""},
                headers={"X-Forwarded-For": "203.0.113.195"}
            )
            self.assertEqual(resp.status_code, 400, f"Request {i+1} failed with unexpected status")

        # 31st request from same IP must return 429 Too Many Requests
        resp_31 = self.client.post(
            "/api/chat",
            data={"message": ""},
            headers={"X-Forwarded-For": "203.0.113.195"}
        )
        self.assertEqual(resp_31.status_code, 429)
        self.assertIn("limit: 30 requests/minute", resp_31.json().get("detail", ""))


if __name__ == "__main__":
    unittest.main()
