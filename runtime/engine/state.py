"""
State models for InsureQuery Runtime.

The runtime state is fully reconstructable from the event log.
No hidden state — the reducer is the single source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Intent:
    """Parsed user intent classification."""

    intent_type: str
    confidence: float
    entities: List[Dict[str, Any]] = field(default_factory=list)
    raw_query: str = ""


@dataclass
class PlanStep:
    """A single step in the execution plan."""

    step_id: int
    tool_name: str
    description: str
    input_params: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    depends_on: List[int] = field(default_factory=list)


@dataclass
class ToolResult:
    """Result of a single tool execution."""

    tool_name: str
    success: bool
    output: Dict[str, Any] = field(default_factory=dict)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class Answer:
    """Final answer produced by the runtime."""

    text: str
    citations: List[Dict[str, Any]] = field(default_factory=list)
    confidence: Optional[float] = None


@dataclass
class RuntimeState:
    """Complete runtime state reconstructed from events.

    This is the canonical state representation. Every field is derived
    by the reducer from the event log — never mutated directly.

    Sprint 3 additions: ontology_context, retrieved_chunks, evidence_graph, retrieval_path
    """

    session_id: str
    query: Optional[str] = None
    intent: Optional[Intent] = None
    plan: List[PlanStep] = field(default_factory=list)
    tool_results: List[ToolResult] = field(default_factory=list)
    answer: Optional[Answer] = None
    event_count: int = 0
    status: str = "created"
    error: Optional[str] = None
    # Sprint 3: Knowledge Layer state
    ontology_context: List[str] = field(default_factory=list)
    retrieved_chunks: List[Dict[str, Any]] = field(default_factory=list)
    evidence_graph: Dict[str, Any] = field(default_factory=dict)
    retrieval_path: List[str] = field(default_factory=list)
    # Sprint 4: Evaluation Layer state
    trace_id: str = ""
    evaluation_result: Dict[str, Any] = field(default_factory=dict)
    hallucination_report: Dict[str, Any] = field(default_factory=dict)
    diagnosis: str = ""
    feedback_signals: List[Dict[str, Any]] = field(default_factory=list)
    # Sprint 5: Production Multi-Agent state
    agent_execution_graph: List[Dict[str, Any]] = field(default_factory=list)
    cache_state: Dict[str, Any] = field(default_factory=dict)
    system_health: Dict[str, Any] = field(default_factory=dict)
    failure_recovery_path: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # v2 Kernel state
    memory_context: Dict[str, Any] = field(default_factory=dict)
    memory_facts: Dict[str, Any] = field(default_factory=dict)
    process_result: Dict[str, Any] = field(default_factory=dict)
    rule_evaluation: Dict[str, Any] = field(default_factory=dict)
    tuning_weights: Dict[str, float] = field(default_factory=dict)
    accepted_evidence_ids: List[str] = field(default_factory=list)
    evidence_selection: Dict[str, Any] = field(default_factory=dict)
    turns: List[Dict[str, Any]] = field(default_factory=list)
    current_turn_index: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "query": self.query,
            "intent": {
                "intent_type": self.intent.intent_type,
                "confidence": self.intent.confidence,
                "entities": self.intent.entities,
                "raw_query": self.intent.raw_query,
            }
            if self.intent
            else None,
            "plan": [
                {
                    "step_id": s.step_id,
                    "tool_name": s.tool_name,
                    "description": s.description,
                    "input_params": s.input_params,
                    "status": s.status,
                }
                for s in self.plan
            ],
            "tool_results": [
                {
                    "tool_name": r.tool_name,
                    "success": r.success,
                    "output": r.output,
                    "evidence": r.evidence,
                    "error": r.error,
                    "duration_ms": r.duration_ms,
                }
                for r in self.tool_results
            ],
            "answer": {
                "text": self.answer.text,
                "citations": self.answer.citations,
                "confidence": self.answer.confidence,
            }
            if self.answer
            else None,
            "event_count": self.event_count,
            "status": self.status,
            "error": self.error,
            # Sprint 3
            "ontology_context": self.ontology_context,
            "retrieved_chunks": self.retrieved_chunks,
            "evidence_graph": self.evidence_graph,
            "retrieval_path": self.retrieval_path,
            # Sprint 4
            "trace_id": self.trace_id,
            "evaluation_result": self.evaluation_result,
            "hallucination_report": self.hallucination_report,
            "diagnosis": self.diagnosis,
            "feedback_signals": self.feedback_signals,
            # Sprint 5
            "agent_execution_graph": self.agent_execution_graph,
            "cache_state": self.cache_state,
            "system_health": self.system_health,
            "failure_recovery_path": self.failure_recovery_path,
            # v2 Kernel
            "memory_context": self.memory_context,
            "memory_facts": self.memory_facts,
            "process_result": self.process_result,
            "rule_evaluation": self.rule_evaluation,
            "tuning_weights": self.tuning_weights,
            "accepted_evidence_ids": self.accepted_evidence_ids,
            "evidence_selection": self.evidence_selection,
            "turns": self.turns,
            "current_turn_index": self.current_turn_index,
        }
