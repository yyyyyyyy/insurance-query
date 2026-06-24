"""Pipeline stage: ontology expansion and hybrid retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, TYPE_CHECKING

from runtime.engine.event_store import ontology_expanded_event, retrieval_executed_event
from runtime.agents.pipeline._helpers import EventSequencer, send_agent

if TYPE_CHECKING:
    from runtime.agents.bus import AgentContext
    from runtime.agents.orchestrator import MultiAgentEngine


@dataclass
class RetrievalStageResult:
    retrieval_chunks: List[Dict[str, Any]]
    decision_trace: List[Dict[str, Any]]
    onto_matches: List[str]
    retrieval_weights: Dict[str, Any]


def run_retrieval_stage(
    engine: "MultiAgentEngine",
    ctx: "AgentContext",
    seq: EventSequencer,
    *,
    trace_id: str,
    resolved_query: str,
    retrieval_query: str,
    intent: Dict[str, Any],
) -> RetrievalStageResult:
    retrieval_weights = engine.tuner.get_retrieval_params()
    retrieval_weights["min_score"] = 0.0
    ctx.retrieval_weights = retrieval_weights

    seed_names = [e.get("value", "") for e in intent.get("entities", [])]
    onto_matches = engine._ontology_expand(seed_names)
    ctx.ontology_context = onto_matches

    if onto_matches:
        seq.append(
            ontology_expanded_event,
            seed_entities=seed_names,
            expanded_entities=onto_matches,
        )

    resp = send_agent(
        engine, ctx, seq, "retrieval", "task",
        {
            "query": retrieval_query,
            "ontology_context": seed_names,
            "memory_context": ctx.memory_context,
            "retrieval_weights": retrieval_weights,
        },
        trace_id,
    )
    retrieval_chunks = resp.payload.get("chunks", [])
    decision_trace = resp.payload.get("decision_trace", [])
    ctx.retrieval_results = retrieval_chunks
    ctx.execution_graph.append({"agent": "retrieval", "chunks": len(retrieval_chunks)})

    seq.append(
        retrieval_executed_event,
        query=retrieval_query,
        result_count=len(retrieval_chunks),
        ontology_used=len(onto_matches) > 0,
        weights=retrieval_weights,
        base_query=resolved_query,
        decision_trace=decision_trace,
        chunks=retrieval_chunks[:10],
    )

    return RetrievalStageResult(
        retrieval_chunks=retrieval_chunks,
        decision_trace=decision_trace,
        onto_matches=onto_matches,
        retrieval_weights=retrieval_weights,
    )
