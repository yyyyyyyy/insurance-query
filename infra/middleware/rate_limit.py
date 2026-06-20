"""
Rate Limiting — Token bucket middleware for FastAPI.

Provides per-IP token bucket rate limiting. Configurable rate, burst,
and burst behavior. Returns 429 Too Many Requests when limit exceeded.

Usage:
    from infra.middleware.rate_limit import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware, rate=10, burst=20)
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


@dataclass
class TokenBucket:
    """Token bucket rate limiter for a single client."""
    tokens: float = 0.0
    last_refill: float = 0.0
    max_tokens: float = 10.0
    refill_rate: float = 1.0  # tokens per second

    def consume(self, tokens: float = 1.0) -> bool:
        now = time.time()
        # Refill
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token bucket rate limiting middleware.

    Tracks per-IP buckets in memory. Configurable via constructor parameters.

    X-Forwarded-For is only trusted when the request originates from a
    trusted proxy. Trusted proxies are configured via TRUSTED_PROXIES env var
    (comma-separated IPs) or are empty by default (safe for direct exposure).
    """

    DEFAULT_RATE = 10  # requests per second
    DEFAULT_BURST = 20  # maximum burst
    CLEANUP_INTERVAL = 60  # seconds between stale client cleanup

    def __init__(
        self,
        app,
        rate: float = DEFAULT_RATE,
        burst: int = DEFAULT_BURST,
    ):
        super().__init__(app)
        self.rate = rate
        self.burst = burst
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.time()

        trusted = os.environ.get("TRUSTED_PROXIES", "")
        self._trusted_proxies: Set[str] = {
            ip.strip() for ip in trusted.split(",") if ip.strip()
        }

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip health/static endpoints
        if request.url.path in ("/health", "/docs", "/openapi.json"):
            return await call_next(request)

        client_ip = self._get_client_ip(request)

        with self._lock:
            self._maybe_cleanup()
            bucket = self._buckets.get(client_ip)
            if bucket is None:
                bucket = TokenBucket(
                    max_tokens=self.burst,
                    refill_rate=self.rate,
                )
                self._buckets[client_ip] = bucket

            if not bucket.consume(1.0):
                retry_after = max(1.0, (1.0 - bucket.tokens) / bucket.refill_rate)
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limited",
                        "message": "Too many requests. Please slow down.",
                        "retry_after_seconds": round(retry_after, 1),
                    },
                    headers={"Retry-After": str(int(retry_after + 1))},
                )

        return await call_next(request)

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP.

        Only trusts X-Forwarded-For when the direct client is a known proxy.
        This prevents IP spoofing when the service is exposed without a
        reverse proxy (e.g. direct uvicorn in docker-compose).
        """
        client_host = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded and client_host in self._trusted_proxies:
            return forwarded.split(",")[0].strip()
        return client_host

    def _maybe_cleanup(self):
        now = time.time()
        if now - self._last_cleanup < self.CLEANUP_INTERVAL:
            return
        self._last_cleanup = now
        # Remove clients inactive for > 5 minutes
        stale = []
        for ip, bucket in list(self._buckets.items()):
            if now - bucket.last_refill > 300:
                stale.append(ip)
        for ip in stale:
            del self._buckets[ip]
        if stale:
            from logging import getLogger
            getLogger(__name__).debug("Cleaned up %d stale rate limit buckets", len(stale))

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "active_clients": len(self._buckets),
                "rate": self.rate,
                "burst": self.burst,
            }
