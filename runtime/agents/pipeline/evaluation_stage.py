"""Pipeline stage: evaluation and tuning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, TYPE_CHECKING

from runtime.engine.event_store import (
    evaluation_completed_event,
    hallucination_detected_event,
    system_degraded_event,
    system_feedback_generated_event,
    tuning_applied_event,
    trace_captured_event,
)
from runtime.agents.bus import AgentStatus
from runtime.agents.pipeline._helpers import EventSequencer, send_agent

if TYPE_CHECKING:
    from runtime.agents.bus import AgentContext
    from runtime.agents.orchestrator import MultiAgentEngine


@dataclass
class EvaluationStageResult:
    eval_result: Dict[str, Any]
    feedback_signals: List[Dict[str, Any]]


def run_evaluation_stage(
    engine: "MultiAgentEngine",
    ctx: "AgentContext",
    seq: EventSequencer,
    *,
    session_id: str,
    trace_id: str,
    resolved_query: str,
) -> EvaluationStageResult:
    events_for_eval = [
        e.to_dict() for e in engine.event_store.get_session_events(session_id)
    ]
    resp = send_agent(
        engine, ctx, seq, "evaluation", "task",
        {
            "session_id": session_id,
            "query": resolved_query,
            "events": events_for_eval,
        },
        trace_id,
    )
    ctx.evaluation = resp.payload
    eval_result = ctx.evaluation

    # Short-circuit on agent error: skip tuning, write degraded event
    if resp.msg_type == "error" or ctx.agent_statuses.get("evaluation") in (
        AgentStatus.FAILED, AgentStatus.DEGRADED,
    ):
        ctx.degraded_mode = True
        seq.append(system_degraded_event, reason="evaluation:failed")
        seq.append(
            evaluation_completed_event,
            total_score=0.0,
            dimensions={},
            diagnosis=eval_result.get("diagnosis", "evaluation agent failed"),
        )
        seq.append(trace_captured_event, trace_id=trace_id)
        return EvaluationStageResult(
            eval_result=eval_result,
            feedback_signals=[],
        )

    if ctx.agent_statuses.get("evaluation") == AgentStatus.DEGRADED:
        ctx.degraded_mode = True
        seq.append(system_degraded_event, reason="evaluation:degraded")

    dimensions = eval_result.get("dimensions", {})
    seq.append(
        evaluation_completed_event,
        total_score=float(eval_result.get("total_score", 0)),
        dimensions=dimensions,
        diagnosis=eval_result.get("diagnosis", ""),
    )
    seq.append(
        hallucination_detected_event,
        hallucination_score=float(eval_result.get("hallucination_score", 0)),
        severity=eval_result.get("severity", "NONE"),
        violations=eval_result.get("violations", []),
    )

    feedback_signals = eval_result.get("feedback", [])
    if feedback_signals:
        seq.append(system_feedback_generated_event, signals=feedback_signals)

    # Only apply tuning when evaluation has valid dimensions
    if dimensions:
        tuning_config = engine.tuner.apply_evaluation(eval_result, feedback_signals)
        seq.append(
            tuning_applied_event,
            weights={
                "bm25_weight": tuning_config.bm25_weight,
                "vector_weight": tuning_config.vector_weight,
                "ontology_weight": tuning_config.ontology_weight,
            },
            reason=tuning_config.last_adjustment,
        )

    seq.append(trace_captured_event, trace_id=trace_id)

    return EvaluationStageResult(
        eval_result=eval_result,
        feedback_signals=feedback_signals,
    )
