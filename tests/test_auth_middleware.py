"""API key middleware tests."""

import asyncio

import pytest
from starlette.requests import Request
from starlette.responses import Response

from infra.middleware.auth import ApiKeyMiddleware


def _request(path: str = "/query", headers: list | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": headers or [],
        "client": ("127.0.0.1", 0),
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_no_key_configured_allows_request(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    mw = ApiKeyMiddleware(app=None)

    async def _next(req):
        return Response("ok")

    resp = await mw.dispatch(_request(), _next)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_wrong_key_returns_401(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret")
    mw = ApiKeyMiddleware(app=None)

    async def _next(req):
        return Response("ok")

    resp = await mw.dispatch(
        _request(headers=[(b"x-api-key", b"wrong")]), _next,
    )
    assert resp.status_code == 401
