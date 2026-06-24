"""
OpenTelemetry Observability — Structured spans for the query pipeline.

Integrates OTel spans into the MultiAgentEngine query pipeline. Each pipeline
step (intent → retrieval → tools → eval) gets its own span with attributes.

Fallback: if opentelemetry is not installed, logs spans via standard logging.

Usage:
    tracer = init_tracer("insurequery-api")
    with tracer.start_as_current_span("query") as span:
        span.set_attribute("query.text", query_text)
        ...
"""

from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_OTEL_AVAILABLE = False
_tracer: Any = None
_init_lock = threading.Lock()


def init_tracer(service_name: str = "insurequery-api"):
    """Initialize OpenTelemetry tracer. Falls back to log-based spans if not installed."""
    global _tracer, _OTEL_AVAILABLE

    with _init_lock:
        if _tracer is not None:
            return _tracer

        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import SimpleSpanProcessor
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import Resource

            resource = Resource.create({"service.name": service_name})
            provider = TracerProvider(resource=resource)

            otlp_endpoint = (
                os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
                or "http://localhost:4318/v1/traces"
            )
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            provider.add_span_processor(SimpleSpanProcessor(exporter))
            trace.set_tracer_provider(provider)

            _tracer = trace.get_tracer(service_name)
            _OTEL_AVAILABLE = True
            logger.info("OpenTelemetry initialized (OTLP -> %s)", otlp_endpoint)

        except ImportError:
            logger.info("opentelemetry not installed. Using log-based span fallback.")
            _tracer = _LogSpanTracer()
        except Exception as exc:
            logger.warning("Failed to init OTel: %s. Using log-based spans.", exc)
            _tracer = _LogSpanTracer()

    return _tracer


class _LogSpanTracer:
    """Fallback tracer that logs span boundaries instead of exporting to OTLP."""

    def __init__(self):
        self._spans: List[Dict[str, Any]] = []
        self._active: Dict[str, float] = {}

    @contextmanager
    def start_as_current_span(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        span_id = f"{name}-{time.time_ns()}"
        self._active[span_id] = time.perf_counter()
        attrs = attributes or {}

        try:
            yield _LogSpan(span_id, name, attrs, self)
        finally:
            start = self._active.pop(span_id, 0)
            duration = time.perf_counter() - start
            span_data = {
                "span_id": span_id, "name": name,
                "attributes": attrs, "duration_ms": round(duration * 1000, 2),
            }
            self._spans.append(span_data)
            if duration > 5.0:
                logger.warning("SLOW span: %s (%.2fs) attrs=%s", name, duration, attrs)
            elif duration > 2.0:
                logger.info("span: %s (%.2fs)", name, duration)

    def get_spans(self) -> List[Dict[str, Any]]:
        return list(self._spans)

    def clear(self):
        self._spans.clear()


class _LogSpan:
    """Minimal span-like object for log-based tracing."""

    def __init__(self, span_id, name, attributes, tracer):
        self._id = span_id
        self._name = name
        self._attributes = dict(attributes)
        self._tracer = tracer

    def set_attribute(self, key: str, value: Any):
        self._attributes[key] = str(value)[:200]

    def set_attributes(self, attributes: Dict[str, Any]):
        for k, v in attributes.items():
            self._attributes[k] = str(v)[:200]

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        pass  # No-op in log fallback


def get_tracer():
    """Get the global tracer (initialized lazily if needed)."""
    global _tracer
    if _tracer is None:
        _tracer = init_tracer()
    return _tracer
