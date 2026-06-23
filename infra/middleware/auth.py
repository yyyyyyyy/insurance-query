"""Optional API key authentication for production deployments."""

from __future__ import annotations

import hmac
import os
from typing import Callable, Optional, Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

_PUBLIC_PATHS: Set[str] = {"/health", "/docs", "/openapi.json", "/redoc"}


def _configured_api_key() -> Optional[str]:
    key = os.environ.get("API_KEY", "").strip()
    return key or None


def _extract_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    header_key = request.headers.get("X-API-Key", "").strip()
    return header_key or None


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Require API_KEY when the env var is set; skip when unset (local dev)."""

    async def dispatch(self, request: Request, call_next: Callable):
        expected = _configured_api_key()
        if not expected or request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        token = _extract_token(request)
        if not hmac.compare_digest(token or "", expected):
            return JSONResponse(
                status_code=401,
                content={
                    "error": "unauthorized",
                    "message": "Valid API key required. Set Authorization: Bearer <key> or X-API-Key.",
                },
            )
        return await call_next(request)
