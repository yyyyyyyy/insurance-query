"""Request ID middleware — correlation IDs for distributed tracing.

Generates (or accepts) a per-request correlation ID and propagates it to
the response headers and to a logging ``LogContext`` so all log lines
emitted while handling a request carry the same ``request_id``. This
makes it trivial to grep server logs for everything that happened during
a single user query.

Usage:
    from infra.middleware.request_id import RequestIdMiddleware
    app.add_middleware(RequestIdMiddleware)
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar
from typing import Callable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"

# ContextVar so any async task / thread running within the request scope
# can read the current request_id for structured logging.
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


class _RequestIdLogFilter(logging.Filter):
    """Inject the current request_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        rid = request_id_var.get()
        record.request_id = rid or "-"
        return True


def install_log_filter() -> None:
    """Attach the request_id filter and handler to root logger (idempotent).

    Uses setLogRecordFactory to inject request_id into every log record,
    avoiding formatter mismatch on child loggers.
    """
    root = logging.getLogger()
    if not any(isinstance(f, _RequestIdLogFilter) for f in root.filters):
        root.addFilter(_RequestIdLogFilter())

    fmt = "%(asctime)s [%(request_id)s] %(name)s %(levelname)s %(message)s"
    needs_default = True
    for h in root.handlers:
        f = h.formatter
        if f and f._fmt and "%(request_id)s" in f._fmt:
            needs_default = False
            break
        if hasattr(h, "formatter") and h.formatter:
            old_fmt = h.formatter
            h.setFormatter(logging.Formatter(
                old_fmt._fmt.replace("%(message)s", "[%(request_id)s] %(message)s")
                if old_fmt._fmt else fmt
            ))
    if needs_default and not any(
        getattr(h, "_request_id_default", False) for h in root.handlers
    ):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(fmt))
        setattr(handler, "_request_id_default", True)
        root.addHandler(handler)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign and propagate a correlation ID for every HTTP request."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        # Honor an upstream proxy/gateway ID if provided, else mint one.
        rid = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        try:
            response: Response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = rid
            return response
        finally:
            request_id_var.reset(token)
