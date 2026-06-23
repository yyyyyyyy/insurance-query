"""Rate limit middleware tests."""

from starlette.requests import Request

from infra.middleware.rate_limit import RateLimitMiddleware, TokenBucket


def _make_request(path: str = "/query", client: str = "10.0.0.1") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [],
        "client": (client, 0),
    }
    return Request(scope)


class TestTokenBucket:
    def test_consume_within_burst(self):
        bucket = TokenBucket(max_tokens=5, refill_rate=10)
        assert bucket.consume()
        assert bucket.consume()


class TestRateLimitMiddleware:
    def test_health_bypasses_limit(self):
        mw = RateLimitMiddleware(app=None, rate=1, burst=1)
        req = _make_request("/health")
        ip = mw._get_client_ip(req)
        assert ip == "10.0.0.1"

    def test_trusted_proxy_forwarded_for(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXIES", "10.0.0.1")
        mw = RateLimitMiddleware(app=None)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/query",
            "headers": [(b"x-forwarded-for", b"203.0.113.5")],
            "client": ("10.0.0.1", 0),
        }
        req = Request(scope)
        assert mw._get_client_ip(req) == "203.0.113.5"
