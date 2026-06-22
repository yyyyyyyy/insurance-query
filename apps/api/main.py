"""
InsureQuery API — FastAPI Service + Runtime Console endpoints.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from runtime.tools.registry import create_default_registry, ToolDispatcher
from runtime.agents.orchestrator import MultiAgentEngine
from infra.db.event_store import SqliteEventStore
from infra.db.session_store import WorkingMemory
from evaluation.feedback.tuner import SelfTuner
from apps.api.console_helpers import build_console_payload
import logging

logger = logging.getLogger(__name__)

app = FastAPI(
    title="InsureQuery AI Runtime Kernel",
    description="Production AI Runtime Infrastructure for Insurance Reasoning",
    version="3.0.0-kernel-v2",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from infra.middleware.rate_limit import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware, rate=10, burst=30)

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

# Last console payload per session (for full retrieval replay)
_session_console_cache: Dict[str, Dict[str, Any]] = {}


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    sessions_processed: int = 0
    total_events: int = 0
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
    result = engine.query(query_text=request.query, session_id=request.session_id)
    wm = result.get("working_memory") or (
        _working_memory.get_context_for_query(result["session_id"]) if _working_memory else {}
    )
    console = build_console_payload(result, wm)
    _session_console_cache[result["session_id"]] = console
    return console


@app.get("/trace/{session_id}", tags=["Runtime"])
async def get_trace(session_id: str):
    return _rebuild_console_from_session(session_id)


@app.get("/sessions", tags=["Runtime"])
async def list_sessions():
    ids = engine.event_store.list_sessions()
    return {"sessions": ids, "count": len(ids)}


@app.get("/sessions/{session_id}", tags=["Runtime"])
async def get_session(session_id: str):
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
    import json as _json
    import asyncio

    async def event_stream():
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, engine.query, request.query, request.session_id
        )
        wm = result.get("working_memory") or {}
        console = build_console_payload(result, wm)
        _session_console_cache[result["session_id"]] = console

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

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    from runtime.llm.config import llm_settings
    llm = llm_settings()
    return HealthResponse(
        status="healthy",
        version="3.0.0-kernel-v2",
        sessions_processed=engine.event_store.session_count(),
        total_events=engine.event_store.count(),
        llm_enabled=llm.is_configured,
        llm_provider=llm.provider if llm.is_configured else None,
        llm_model=llm.model if llm.is_configured else None,
    )


@app.get("/stats", tags=["System"])
async def system_stats():
    return engine.stats()


@app.get("/dashboard", tags=["System"])
async def dashboard():
    from infra.observability.monitor import ObservabilityLayer
    obs = ObservabilityLayer()
    obs.metrics.record_query(100, "init")
    return {
        "agent_statuses": engine.bus.agent_statuses(),
        "async_executor": engine.async_exec.stats(),
        "cache": engine.cache.stats(),
        "tuning": engine.tuner.stats(),
    }


@app.get("/events", tags=["Debug"])
async def list_all_events():
    return {
        "message_count": len(engine.bus.message_log()),
        "messages": engine.bus.message_log(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("apps.api.main:app", host="0.0.0.0", port=8000, reload=True)
