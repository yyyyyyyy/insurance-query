"""
Trace Capture System — Immutable execution record for every query.

SPRINT 4 RULE #2: No answer without trace.
SPRINT 4 RULE #1: Evaluation is not optional.

The trace is the foundation of the self-evaluating system.
Every query produces a complete, immutable trace that feeds evaluation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class QueryTrace:
    """Complete, immutable execution trace for a single query.

    Contains every decision point from query to answer, enabling:
      - Replay verification
      - Quality scoring
      - Hallucination detection
      - Feedback generation
    """

    trace_id: str
    session_id: str
    query: str
    timestamp: str

    # Pipeline stages
    intent: Dict[str, Any] = field(default_factory=dict)
    ontology_expansion: Dict[str, Any] = field(default_factory=dict)
    retrieval_results: List[Dict[str, Any]] = field(default_factory=list)
    plan_steps: List[Dict[str, Any]] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    evidence_items: List[Dict[str, Any]] = field(default_factory=list)
    evidence_graph: Dict[str, Any] = field(default_factory=dict)
    final_answer: Dict[str, Any] = field(default_factory=dict)
    runtime_events: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata
    total_latency_ms: float = 0.0
    tool_call_count: int = 0
    evidence_count: int = 0
    accepted_evidence_count: int = 0
    ontology_entities_used: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "query": self.query,
            "timestamp": self.timestamp,
            "intent": self.intent,
            "ontology_expansion": self.ontology_expansion,
            "retrieval_results": self.retrieval_results,
            "plan_steps": self.plan_steps,
            "tool_calls": self.tool_calls,
            "evidence_items": self.evidence_items,
            "evidence_graph": self.evidence_graph,
            "final_answer": self.final_answer,
            "runtime_events": self.runtime_events,
            "total_latency_ms": self.total_latency_ms,
            "tool_call_count": self.tool_call_count,
            "evidence_count": self.evidence_count,
            "accepted_evidence_count": self.accepted_evidence_count,
            "ontology_entities_used": self.ontology_entities_used,
        }


class TraceCapture:
    """Captures execution trace from runtime events.

    Extracts structured trace from the event-sourced log.
    Trace is immutable — once captured, it does not change.
    """

    def __init__(self):
        self._traces: Dict[str, QueryTrace] = {}

    def capture(
        self,
        session_id: str,
        query: str,
        runtime_events: List[Dict[str, Any]],
        state: Dict[str, Any],
        latency_ms: float = 0.0,
    ) -> QueryTrace:
        """Capture a complete trace from runtime output.

        Extracts intent, plan, tool calls, evidence, and answer
        from the event stream and runtime state.
        """
        trace = QueryTrace(
            trace_id=f"TRC-{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            query=query,
            timestamp=datetime.now(timezone.utc).isoformat(),
            runtime_events=runtime_events,
            total_latency_ms=latency_ms,
        )

        # Extract from state
        trace.intent = state.get("intent") or {}
        trace.evidence_graph = state.get("evidence_graph") or {}
        trace.final_answer = state.get("answer") or {}
        trace.ontology_expansion = {
            "context": state.get("ontology_context", []),
            "path": state.get("retrieval_path", []),
        }
        trace.ontology_entities_used = len(state.get("ontology_context", []))

        # Extract from events
        for event in runtime_events:
            et = event.get("event_type", "")
            payload = event.get("payload", {})

            if et == "INTENT_CLASSIFIED":
                trace.intent = payload
            elif et == "PLAN_CREATED":
                trace.plan_steps = payload.get("plan", [])
            elif et == "TOOL_CALLED":
                trace.tool_calls.append({
                    "tool_name": payload.get("tool_name", ""),
                    "input_params": payload.get("input_params", {}),
                })
                trace.tool_call_count += 1
            elif et == "EVIDENCE_FOUND":
                ev_items = payload.get("evidence", [])
                trace.evidence_items.extend(ev_items)
            elif et == "EVIDENCE_SELECTED":
                trace.accepted_evidence_count = len(payload.get("accepted_ids", []))
                for snap in payload.get("snapshot", []):
                    if snap.get("stage") == "accepted":
                        trace.evidence_items.append(snap.get("payload", snap))
            elif et == "RETRIEVAL_EXECUTED":
                trace.retrieval_results.append({
                    "query": payload.get("query", ""),
                    "base_query": payload.get("base_query", ""),
                    "result_count": payload.get("result_count", 0),
                    "ontology_used": payload.get("ontology_used", False),
                    "decision_trace": payload.get("decision_trace", []),
                })
            elif et == "CACHE_HIT":
                trace.retrieval_results.append({
                    "query": payload.get("key", ""),
                    "result_count": 0,
                    "ontology_used": False,
                    "from_cache": True,
                    "source_trace_id": payload.get("source_trace_id", ""),
                })
            elif et == "ONTOLOGY_EXPANDED":
                expanded = (
                    payload.get("expanded_entities")
                    or payload.get("seed_entities")
                    or []
                )
                trace.ontology_expansion = {
                    "context": expanded,
                    "path": payload.get("path", []),
                    "seed_entities": payload.get("seed_entities", []),
                }
                trace.ontology_entities_used = len(expanded)
            elif et == "ANSWER_GENERATED":
                trace.final_answer = {
                    "text": payload.get("answer", ""),
                    "citations": payload.get("citations", []),
                    "confidence": payload.get("confidence"),
                    "accepted_evidence_ids": payload.get("accepted_evidence_ids", []),
                    "used_in_answer_ids": payload.get("used_in_answer_ids", []),
                }
                if payload.get("used_in_answer_ids"):
                    trace.accepted_evidence_count = len(payload["used_in_answer_ids"])

        if not trace.final_answer.get("text"):
            degraded_answer = state.get("answer") or {}
            if degraded_answer:
                trace.final_answer = degraded_answer
        if not trace.intent:
            degraded_intent = state.get("intent") or {}
            if degraded_intent:
                trace.intent = degraded_intent
        if not trace.ontology_expansion.get("context") and state.get("ontology_context"):
            trace.ontology_expansion = {
                "context": state.get("ontology_context", []),
                "path": state.get("retrieval_path", []),
            }
            trace.ontology_entities_used = len(state.get("ontology_context", []))

        trace.evidence_count = max(
            len(trace.evidence_items),
            trace.accepted_evidence_count,
        )
        self._traces[trace.trace_id] = trace
        return trace

    def get_trace(self, trace_id: str) -> Optional[QueryTrace]:
        return self._traces.get(trace_id)

    def get_traces_by_session(self, session_id: str) -> List[QueryTrace]:
        return [t for t in self._traces.values() if t.session_id == session_id]

    def all_traces(self) -> List[QueryTrace]:
        return list(self._traces.values())

    def trace_count(self) -> int:
        return len(self._traces)
