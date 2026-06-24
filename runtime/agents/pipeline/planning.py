"""Pipeline stage: intent classification and plan creation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, TYPE_CHECKING

from runtime.engine.event_store import intent_classified_event, plan_created_event
from runtime.agents.pipeline._helpers import EventSequencer, send_agent

if TYPE_CHECKING:
    from runtime.agents.bus import AgentContext
    from runtime.agents.orchestrator import MultiAgentEngine


@dataclass
class PlanningResult:
    intent: Dict[str, Any]
    plan: List[Dict[str, Any]]
    intent_type: str


def run_planning_stage(
    engine: "MultiAgentEngine",
    ctx: "AgentContext",
    seq: EventSequencer,
    *,
    session_id: str,
    trace_id: str,
    resolved_query: str,
    memory_context: Dict[str, Any],
    injected_entities: List[Dict[str, Any]],
) -> PlanningResult:
    resp = send_agent(
        engine, ctx, seq, "planner", "task",
        {
            "query": resolved_query,
            "memory_context": memory_context,
            "injected_entities": injected_entities,
        },
        trace_id,
    )
    intent = resp.payload.get("intent", {})
    plan = resp.payload.get("plan", resp.payload.get("fallback_plan", []))
    ctx.intent = intent
    ctx.plan = plan
    ctx.execution_graph.append({
        "agent": "planner",
        "intent": intent.get("intent"),
        "plan_len": len(plan),
    })

    seq.append(
        intent_classified_event,
        intent=intent.get("intent", "general_inquiry"),
        confidence=intent.get("confidence", 0.5),
        entities=intent.get("entities", []),
    )
    seq.append(
        plan_created_event,
        plan=plan,
        reasoning=f"Plan for intent: {intent.get('intent', 'general_inquiry')}",
    )

    return PlanningResult(
        intent=intent,
        plan=plan,
        intent_type=intent.get("intent", "general_inquiry"),
    )
