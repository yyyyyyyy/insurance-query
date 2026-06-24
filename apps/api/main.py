"""
InsureQuery API — FastAPI Service + Runtime Console endpoints.
"""

from __future__ import annotations

from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional, Annotated
import asyncio

from fastapi import FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from runtime.tools.registry import create_default_registry, ToolDispatcher
from runtime.agents.orchestrator import MultiAgentEngine
from infra.db.event_store import SqliteEventStore
from infra.db.session_store import WorkingMemory
from evaluation.feedback.tuner import SelfTuner
from apps.api.console_helpers import build_console_payload
import logging

logger = logging.getLogger(__name__)

SessionIdPath = Annotated[
    str,
    Path(max_length=64, pattern=r"^[a-zA-Z0-9_-]+$", description="Session identifier"),
]


def _create_app() -> FastAPI:
    """Application factory wiring engine and lifespan handlers."""

    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        # Warm up the knowledge graph + retriever in a background thread so
        # the server (and test clients using this lifespan) become ready
        # immediately. ``_ensure_knowledge`` is idempotent and guards on
        # ``_knowledge_loaded``, so the first real query will simply wait
        # for or join the in-flight warmup.
        #
        # NOTE: the thread is a daemon so it never blocks process exit. This
        # is safe today because warmup builds in-memory structures only. If
        # warmup ever writes persistent artifacts (e.g. a chromadb index to
        # disk), switch to a non-daemon thread with a graceful shutdown
        # signal to avoid leaving half-written files behind.
        import threading

        def _warmup():
            try:
                from infra.observability.telemetry import init_tracer
                init_tracer("insurequery-api")
                engine._ensure_knowledge()
                logger.info("Knowledge preloaded at startup")
            except Exception as exc:
                logger.warning("Knowledge warmup failed (will lazy-load): %s", exc)

        threading.Thread(target=_warmup, name="knowledge-warmup", daemon=True).start()
        yield

    return FastAPI(
        title="InsureQuery AI Runtime Kernel",
        description="Production AI Runtime Infrastructure for Insurance Reasoning",
        version="3.0.0",
        lifespan=_lifespan,
    )


app = _create_app()

def _cors_origins() -> list:
    """CORS allowed origins, configurable via CORS_ORIGINS env var.

    Accepts a comma-separated list, e.g.
    ``CORS_ORIGINS=https://app.example.com,https://staging.example.com``.
    Falls back to the local development origins when unset.

    NOTE: evaluated once at module import time, so the env var must be set
    before the app starts (standard for containerized deployments). Hot
    reconfiguration at runtime is not supported.
    """
    import os
    raw = os.environ.get("CORS_ORIGINS", "").strip()
    if not raw:
        return ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"]
    return [o.strip() for o in raw.split(",") if o.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

from infra.middleware.rate_limit import RateLimitMiddleware
from infra.middleware.request_id import RequestIdMiddleware, install_log_filter
from infra.middleware.auth import ApiKeyMiddleware
app.add_middleware(RateLimitMiddleware, rate=10, burst=30)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(ApiKeyMiddleware)

# Make every log record carry the current request_id (correlation ID).
install_log_filter()

registry = create_default_registry()
dispatcher = ToolDispatcher(registry)
_persistent_store = SqliteEventStore(db_path="data/events.db")
_working_memory = WorkingMemory()
_tuner = SelfTuner()

engine = MultiAgentEngine(
    dispatcher=dispatcher,
    event_store=_persistent_store,
    working_memory=_working_memory,
    tuner=_tuner,
)

# Bounded LRU cache of console payloads per session, to avoid unbounded
# memory growth in long-running processes.
_CONSOLE_CACHE_MAX_ENTRIES = 256
_session_console_cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()


def _cache_console(session_id: str, payload: Dict[str, Any]) -> None:
    """Store a console payload in the LRU cache, evicting oldest if needed."""
    _session_console_cache[session_id] = payload
    _session_console_cache.move_to_end(session_id)
    while len(_session_console_cache) > _CONSOLE_CACHE_MAX_ENTRIES:
        _session_console_cache.popitem(last=False)


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = Field(
        None, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$",
    )


class HealthResponse(BaseModel):
    status: str
    version: str
    sessions_processed: int = 0
    total_events: int = 0
    knowledge_ready: bool = False
    llm_enabled: bool = False
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None


def _rebuild_console_from_session(session_id: str) -> Dict[str, Any]:
    """Rebuild console payload from persisted events + working memory."""
    events = engine.get_session_trace(session_id)
    if not events:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    if session_id in _session_console_cache:
        cached = _session_console_cache[session_id]
        _session_console_cache.move_to_end(session_id)
        cached["event_trace"] = events
        cached["trace"] = build_console_payload({**cached, "event_trace": events})["trace"]
        return cached

    wm = _working_memory.get_context_for_query(session_id) if _working_memory else {}
    pseudo = {
        "session_id": session_id,
        "event_trace": events,
        "execution_graph": [],
        "memory_context": wm,
        "working_memory": wm,
        "tuning": engine.tuner.stats(),
    }
    return build_console_payload(pseudo, wm)


@app.post("/query", tags=["Runtime"])
async def process_query(request: QueryRequest):
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: engine.query(request.query, request.session_id),
    )
    wm = result.get("working_memory") or (
        _working_memory.get_context_for_query(result["session_id"]) if _working_memory else {}
    )
    console = build_console_payload(result, wm)
    _cache_console(result["session_id"], console)
    return console


@app.get("/trace/{session_id}", tags=["Runtime"])
async def get_trace(session_id: SessionIdPath):
    if not _debug_endpoints_enabled():
        return Response(status_code=404)
    return _rebuild_console_from_session(session_id)


@app.get("/sessions", tags=["Runtime"])
async def list_sessions():
    if not _debug_endpoints_enabled():
        return Response(status_code=404)
    ids = engine.event_store.list_sessions()
    return {"sessions": ids, "count": len(ids)}


@app.get("/sessions/{session_id}", tags=["Runtime"])
async def get_session(session_id: SessionIdPath):
    if not _debug_endpoints_enabled():
        return Response(status_code=404)
    console = _rebuild_console_from_session(session_id)
    ctx = _working_memory.get_or_create(session_id) if _working_memory else None
    return {
        **console,
        "agents": engine.bus.agent_statuses(),
        "message_log": engine.bus.message_log(),
        "session_history": ctx.history if ctx else [],
        "query_count": ctx.query_count if ctx else 0,
    }


@app.post("/query/stream", tags=["Runtime"])
async def process_query_stream(request: QueryRequest):
    """非增量流式：整体延迟与 ``POST /query`` 相同，仅提供 SSE 心跳与分阶段事件。

    Stream query results as Server-Sent Events.

    NOTE: this endpoint runs the full pipeline to completion and then emits
    phase events, so overall latency matches ``POST /query``. The advantage
    is that clients receive a heartbeat while waiting (avoiding proxy idle
    timeouts) and structured phase events instead of a single JSON blob.
    """
    import json as _json
    import asyncio

    async def event_stream():
        loop = asyncio.get_running_loop()
        # Run the blocking engine in a worker thread while emitting
        # keep-alive comments so intermediate proxies don't time out.
        task = loop.run_in_executor(
            None, engine.query, request.query, request.session_id
        )
        while not task.done():
            yield ": keep-alive\n\n"
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
            except asyncio.TimeoutError:
                continue
        result = task.result()
        wm = result.get("working_memory") or {}
        console = build_console_payload(result, wm)
        _cache_console(result["session_id"], console)

        phases = [
            ("intent", {"answer_intent": result["answer"].get("intent", "")}),
            ("retrieval", {"total": console["retrieval"].get("total", 0)}),
            ("tools", {"execution_graph": result.get("execution_graph", [])}),
            ("answer", {"text": result["answer"].get("text", "")[:200]}),
            ("evaluation", {"total_score": result.get("evaluation", {}).get("total_score", 0)}),
            ("done", {"trace_id": result.get("trace_id", ""), "session_id": result.get("session_id")}),
        ]
        for phase, data in phases:
            yield f"event: {phase}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    from runtime.llm.config import llm_settings
    llm = llm_settings()
    return HealthResponse(
        status="healthy",
        version="3.0.0",
        sessions_processed=engine.event_store.session_count(),
        total_events=engine.event_store.count(),
        knowledge_ready=getattr(engine, "_knowledge_loaded", False),
        llm_enabled=llm.is_configured,
        llm_provider=llm.provider if llm.is_configured else None,
        llm_model=llm.model if llm.is_configured else None,
    )


def _debug_endpoints_enabled() -> bool:
    import os
    return os.environ.get("DEBUG_ENDPOINTS", "").lower() in {"1", "true", "yes"}


@app.get("/stats", tags=["System"])
async def system_stats():
    if not _debug_endpoints_enabled():
        raise HTTPException(
            status_code=404,
            detail="Debug endpoints disabled. Set DEBUG_ENDPOINTS=1 to enable.",
        )
    return engine.stats()


@app.get("/dashboard", tags=["System"])
async def dashboard():
    if not _debug_endpoints_enabled():
        raise HTTPException(
            status_code=404,
            detail="Debug endpoints disabled. Set DEBUG_ENDPOINTS=1 to enable.",
        )
    return {
        "agent_statuses": engine.bus.agent_statuses(),
        "async_executor": engine.async_exec.stats(),
        "cache": engine.cache.stats(),
        "tuning": engine.tuner.stats(),
        "observability": engine.observability.metrics.snapshot(),
    }


@app.get("/events", tags=["Debug"])
async def list_all_events():
    # Internal agent message log may contain errors, params, and internal
    # payloads. Gate it behind DEBUG_ENDPOINTS so it is disabled by default
    # in production.
    if not _debug_endpoints_enabled():
        raise HTTPException(
            status_code=404,
            detail="Debug endpoints disabled. Set DEBUG_ENDPOINTS=1 to enable.",
        )
    return {
        "message_count": len(engine.bus.message_log()),
        "messages": engine.bus.message_log(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("apps.api.main:app", host="0.0.0.0", port=8000, reload=True)
