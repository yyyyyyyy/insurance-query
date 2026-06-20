"""
InsureQuery API — FastAPI Service

Endpoint:
    POST /query           — Process an insurance query
    GET  /sessions/{id}   — Retrieve session trace
    GET  /health          — Health check

This is the entry point of the InsureQuery AI Runtime Kernel.
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from runtime.tools.registry import create_default_registry, ToolDispatcher
from runtime.agents.orchestrator import MultiAgentEngine
from infra.db.event_store import SqliteEventStore
from infra.db.session_store import WorkingMemory
from evaluation.feedback.tuner import SelfTuner
import logging

logger = logging.getLogger(__name__)

app = FastAPI(
    title="InsureQuery AI Runtime Kernel",
    description="Production AI Runtime Infrastructure for Insurance Reasoning",
    version="2.0.0-sprint8",
)

# Rate limiting middleware
from infra.middleware.rate_limit import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware, rate=10, burst=30)

registry = create_default_registry()
dispatcher = ToolDispatcher(registry)

# Persistence layers
_persistent_store = SqliteEventStore(db_path="data/events.db")
logger.info("Using SQLite-backed EventStore at data/events.db")
_working_memory = WorkingMemory()
_tuner = SelfTuner()

engine = MultiAgentEngine(
    dispatcher=dispatcher,
    event_store=_persistent_store,
    working_memory=_working_memory,
)


# --- Request/Response Models ---


class QueryRequest(BaseModel):
    query: str = Field(..., description="Natural language insurance query", min_length=1, max_length=2000)
    session_id: Optional[str] = Field(None, description="Optional session identifier for traceability")


class QueryResponse(BaseModel):
    session_id: str
    trace_id: str = ""
    query: str = ""
    answer: dict
    evaluation: dict = Field(default_factory=dict)
    execution_graph: list = Field(default_factory=list)
    agent_statuses: dict = Field(default_factory=dict)
    message_log: list = Field(default_factory=list)
    latency_ms: float = 0.0
    cached: bool = False


class HealthResponse(BaseModel):
    status: str
    version: str
    sessions_processed: int = 0
    total_events: int = 0
    llm_enabled: bool = False
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None


# --- Endpoints ---


@app.post("/query", response_model=QueryResponse, tags=["Runtime"])
async def process_query(request: QueryRequest):
    """Process an insurance query through the full runtime pipeline.

    Pipeline: UserQuery → Intent → Plan → Tool Execution → Evidence → Answer

    Returns the answer with full traceability via the event log.
    """
    result = engine.query(query_text=request.query, session_id=request.session_id)

    # Auto-tune based on evaluation
    if result.get("evaluation"):
        _tuner.apply_evaluation(result["evaluation"])
        result["tuning"] = _tuner.stats()

    return QueryResponse(**result)


@app.post("/query/stream", tags=["Runtime"])
async def process_query_stream(request: QueryRequest):
    """Serve-Sent Events (SSE) streaming endpoint.

    Streams pipeline events as they happen. Returns SSE format:
      event: phase
      data: {"phase": "intent", ...}

    Phases: intent, retrieval, tools, answer, evaluation, done
    """
    import json as _json
    import asyncio

    async def event_stream():
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, engine.query, request.query, request.session_id
        )

        phases = [
            ("intent", {"answer_intent": result["answer"].get("intent", "")}),
            ("retrieval", {"evidence_count": result["answer"].get("evidence_count", 0)}),
            ("tools", {"execution_graph": result.get("execution_graph", [])}),
            ("answer", {"text": result["answer"].get("text", ""), "confidence": result["answer"].get("confidence", 0)}),
            ("evaluation", {"total_score": result.get("evaluation", {}).get("total_score", 0)}),
            ("done", {"trace_id": result.get("trace_id", "")}),
        ]

        for phase, data in phases:
            yield f"event: {phase}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """System health check."""
    from runtime.llm.config import llm_settings
    llm = llm_settings()
    return HealthResponse(
        status="healthy",
        version="2.0.0-sprint8",
        sessions_processed=engine.event_store.session_count(),
        total_events=engine.event_store.count(),
        llm_enabled=llm.is_configured,
        llm_provider=llm.provider if llm.is_configured else None,
        llm_model=llm.model if llm.is_configured else None,
    )


@app.get("/stats", tags=["System"])
async def system_stats():
    """Multi-agent system statistics."""
    return engine.stats()


@app.get("/dashboard", tags=["System"])
async def dashboard():
    """System dashboard with metrics and agent status."""
    from infra.observability.monitor import ObservabilityLayer
    obs = ObservabilityLayer()
    obs.metrics.record_query(100, "init")
    return {
        "agent_statuses": engine.bus.agent_statuses(),
        "async_executor": engine.async_exec.stats(),
        "cache": engine.cache.stats(),
    }


@app.get("/sessions/{session_id}", tags=["Debug"])
async def get_session_trace(session_id: str):
    """Retrieve agent message log and execution trace."""
    return {
        "session_id": session_id,
        "agents": engine.bus.agent_statuses(),
        "message_log": engine.bus.message_log(),
    }


@app.get("/events", tags=["Debug"])
async def list_all_events():
    """List agent message log (debug endpoint)."""
    return {
        "message_count": len(engine.bus.message_log()),
        "messages": engine.bus.message_log(),
    }


# --- Entry point ---

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("apps.api.main:app", host="0.0.0.0", port=8000, reload=True)
