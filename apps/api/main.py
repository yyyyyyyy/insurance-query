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
from pydantic import BaseModel, Field

from runtime.tools.registry import create_default_registry, ToolDispatcher
from runtime.agents.orchestrator import MultiAgentEngine

app = FastAPI(
    title="InsureQuery AI Runtime Kernel",
    description="Production AI Runtime Infrastructure for Insurance Reasoning",
    version="1.0.0-sprint5",
)

registry = create_default_registry()
dispatcher = ToolDispatcher(registry)
engine = MultiAgentEngine(dispatcher=dispatcher)


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
    return QueryResponse(**result)


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """System health check."""
    from runtime.llm.config import llm_settings
    llm = llm_settings()
    return HealthResponse(
        status="healthy",
        version="1.0.0-sprint5",
        sessions_processed=0,
        total_events=0,
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
