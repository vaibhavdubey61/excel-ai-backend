"""
rate_limiter.py
===============
Enterprise Distributed Redis-based Rate Limiter for FastAPI.

Architecture:
- Distributed Rate Limiting via Redis backend and FastAPILimiter.
- Fail-Open Resiliency: If Redis is temporarily unreachable or fails under load,
  the limiter logs a CRITICAL error and falls back to an in-memory sliding-window limiter,
  guaranteeing zero downtime for students unless STRICT_RATE_LIMIT=true is explicitly configured.
- Supports IP-based identification (x-forwarded-for, x-real-ip, client.host) and API key headers.
- Enforces 30 requests/minute by default.
"""

import os
import time
import logging
from typing import Optional, Callable
from collections import defaultdict
from functools import wraps

from fastapi import Request, HTTPException, Depends
import redis.asyncio as aioredis
from fastapi_limiter import FastAPILimiter

logger = logging.getLogger("excel_ai.rate_limiter")

DEFAULT_REDIS_URL = "redis://localhost:6379/0"
REDIS_URL = os.getenv("REDIS_URL", DEFAULT_REDIS_URL)
STRICT_RATE_LIMIT = os.getenv("STRICT_RATE_LIMIT", "false").lower() in ("true", "1", "yes")

# Lua script for atomic sliding/fixed window in Redis (matching FastAPILimiter specification)
LUA_RATE_LIMIT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local expire_time = tonumber(ARGV[2])

local current = tonumber(redis.call('get', key) or "0")
if current > 0 then
    if current + 1 > limit then
        return redis.call("PTTL", key)
    else
        redis.call("INCR", key)
        return 0
    end
else
    redis.call("SET", key, 1, "px", expire_time)
    return 0
end
"""


class InMemoryFallbackLimiter:
    """Sliding window in-memory limiter used as fail-open fallback."""

    def __init__(self, requests_limit: int = 30, window_seconds: int = 60):
        self.requests_limit = requests_limit
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)

    def is_allowed(self, identifier: str) -> bool:
        now = time.time()
        timestamps = [ts for ts in self.requests[identifier] if now - ts < self.window_seconds]
        if len(timestamps) >= self.requests_limit:
            self.requests[identifier] = timestamps
            return False
        timestamps.append(now)
        self.requests[identifier] = timestamps
        return True

    def reset(self):
        """Clears in-memory history (useful in tests)."""
        self.requests.clear()


class DistributedRateLimiter:
    """
    Distributed Redis-backed rate limiter with fail-open capability.
    """

    def __init__(
        self,
        redis_url: str = REDIS_URL,
        strict: bool = STRICT_RATE_LIMIT,
        default_limit: int = 30,
        default_window_seconds: int = 60,
    ):
        self.redis_url = redis_url
        self.strict = strict
        self.default_limit = default_limit
        self.default_window_seconds = default_window_seconds
        self.redis_client: Optional[aioredis.Redis] = None
        self._redis_available: bool = False
        self._lua_sha: Optional[str] = None
        self.fallback_limiter = InMemoryFallbackLimiter(
            requests_limit=default_limit,
            window_seconds=default_window_seconds
        )

    def is_redis_available(self) -> bool:
        return self._redis_available and self.redis_client is not None

    async def init(self) -> bool:
        """
        Initializes Redis connection and FastAPILimiter during FastAPI lifespan startup.
        Implements fail-open strategy if Redis is unreachable unless STRICT_RATE_LIMIT=true.
        """
        try:
            self.redis_client = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2.0,
                socket_timeout=2.0
            )
            # Test connectivity
            await self.redis_client.ping()

            # Initialize FastAPILimiter
            await FastAPILimiter.init(self.redis_client, prefix="excel-ai-limiter")
            self._lua_sha = await self.redis_client.script_load(LUA_RATE_LIMIT)
            self._redis_available = True

            print(f"[RateLimiter]: Connected to Redis ({self.redis_url}) successfully. FastAPILimiter initialized.")
            logger.info(f"Connected to Redis ({self.redis_url}) successfully. FastAPILimiter initialized.")
            return True
        except Exception as e:
            self._redis_available = False
            self.redis_client = None
            err_msg = f"Failed to connect to Redis at {self.redis_url}: {e}"
            if self.strict:
                print(f"[RateLimiter Critical]: {err_msg}. STRICT_RATE_LIMIT is enabled. Aborting startup.")
                logger.critical(f"{err_msg}. STRICT_RATE_LIMIT is enabled. Aborting startup.")
                raise
            else:
                print(f"[RateLimiter Critical]: {err_msg}. STRICT_RATE_LIMIT=false. Fail-open strategy active: falling back to in-memory rate limiter.")
                logger.critical(f"{err_msg}. STRICT_RATE_LIMIT=false. Fail-open strategy active: falling back to in-memory rate limiter.")
                return False

    async def close(self):
        """Closes Redis connection on application shutdown."""
        if self.redis_client:
            try:
                await self.redis_client.close()
            except Exception as e:
                logger.warning(f"Error closing Redis client: {e}")
            self.redis_client = None
            self._redis_available = False

    def get_identifier(self, request: Request) -> str:
        """Extracts client IP or API key for rate limit keying."""
        # 1. API key if provided
        api_key = request.headers.get("x-api-key")
        if api_key:
            return f"key:{api_key.strip()}"

        # 2. Forwarded client IP (e.g. from Render / Cloudflare / Nginx proxy)
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
            if client_ip:
                return f"ip:{client_ip}"

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return f"ip:{real_ip.strip()}"

        # 3. Direct client host
        if request.client and request.client.host:
            return f"ip:{request.client.host}"

        return "ip:unknown"

    async def check(
        self,
        request: Request,
        limit: Optional[int] = None,
        window_seconds: Optional[int] = None,
    ) -> bool:
        """
        Checks rate limit for current request.
        Returns True if allowed.
        Raises HTTPException(429) if exceeded.
        Fails open if Redis errors out, unless strict=True.
        """
        req_limit = limit or self.default_limit
        req_window = window_seconds or self.default_window_seconds
        identifier = self.get_identifier(request)

        # 1. Check via Redis if connected
        if self.is_redis_available():
            try:
                key = f"excel-ai-limiter:{identifier}:{request.url.path}"
                expire_ms = req_window * 1000

                if self._lua_sha:
                    try:
                        pexpire = await self.redis_client.evalsha(
                            self._lua_sha, 1, key, str(req_limit), str(expire_ms)
                        )
                    except Exception:
                        # Reload script if evicted from Redis cache
                        self._lua_sha = await self.redis_client.script_load(LUA_RATE_LIMIT)
                        pexpire = await self.redis_client.evalsha(
                            self._lua_sha, 1, key, str(req_limit), str(expire_ms)
                        )
                else:
                    pexpire = await self.redis_client.eval(
                        LUA_RATE_LIMIT, 1, key, str(req_limit), str(expire_ms)
                    )

                if pexpire and int(pexpire) > 0:
                    retry_after = max(1, int(pexpire) // 1000)
                    raise HTTPException(
                        status_code=429,
                        detail=f"Too many requests. Please slow down (limit: {req_limit} requests/minute).",
                        headers={"Retry-After": str(retry_after)},
                    )
                return True
            except HTTPException:
                raise
            except Exception as redis_err:
                err_msg = f"Redis rate limit check error ({redis_err}). Fail-open={not self.strict}."
                print(f"[RateLimiter Critical]: {err_msg}")
                logger.critical(err_msg)
                if self.strict:
                    raise HTTPException(
                        status_code=503,
                        detail="Rate limiter service temporarily unavailable."
                    )
                # Fail open to in-memory fallback below

        # 2. Fallback to in-memory limiter (fail-open or local development)
        if not self.fallback_limiter.is_allowed(identifier):
            raise HTTPException(
                status_code=429,
                detail=f"Too many requests. Please slow down (limit: {req_limit} requests/minute).",
            )
        return True

    def limit(self, rate_string: str = "30/minute"):
        """
        Decorator / Dependency for route endpoints matching @limiter.limit("30/minute").
        """
        parts = rate_string.split("/")
        limit_val = int(parts[0]) if len(parts) > 0 else 30
        unit = parts[1].lower() if len(parts) > 1 else "minute"

        window_seconds = 60
        if "second" in unit:
            window_seconds = 1
        elif "hour" in unit:
            window_seconds = 3600
        elif "day" in unit:
            window_seconds = 86400

        async def dependency(request: Request):
            await self.check(request, limit=limit_val, window_seconds=window_seconds)

        return Depends(dependency)


# Singleton instance
rate_limiter = DistributedRateLimiter()


def get_rate_limiter() -> DistributedRateLimiter:
    return rate_limiter
