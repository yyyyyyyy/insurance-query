"""
State Reducer — Pure function that reconstructs RuntimeState from events.

ARCHITECTURE RULE #3: State is reconstructed via reducer. No direct state mutation.

The reducer is a pure function: given the same event sequence, it always
produces the identical state. This enables deterministic replay and debugging.
"""

from __future__ import annotations

from typing import List

from runtime.engine.event_store import Event, EventType
from runtime.engine.state import Answer, Intent, PlanStep, RuntimeState, ToolResult


def reduce(session_id: str, events: List[Event]) -> RuntimeState:
    """Rebuild runtime state from an ordered list of events.

    This is the core of the event-sourcing pattern. The reducer walks
    through every event in sequence and builds the current state, with
    no side effects and no external dependencies.

    Args:
        session_id: The session to rebuild state for.
        events: Ordered list of events (oldest first).

    Returns:
        A fully reconstructed RuntimeState.
    """
    state = RuntimeState(session_id=session_id)

    for event in events:
        state.event_count += 1
        _apply_event(state, event)

    return state


def _apply_event(state: RuntimeState, event: Event) -> None:
    """Apply a single event to the state (internal dispatch)."""

    handlers = {
        EventType.USER_QUERY: _apply_user_query,
        EventType.INTENT_CLASSIFIED: _apply_intent_classified,
        EventType.PLAN_CREATED: _apply_plan_created,
        EventType.TOOL_CALLED: _apply_tool_called,
        EventType.EVIDENCE_FOUND: _apply_evidence_found,
        EventType.EVIDENCE_SELECTED: _apply_evidence_selected,
        EventType.ANSWER_GENERATED: _apply_answer_generated,
        # Sprint 3: Knowledge Layer
        EventType.CHUNK_CREATED: _apply_chunk_created,
        EventType.ONTOLOGY_EXPANDED: _apply_ontology_expanded,
        EventType.EVIDENCE_INDEXED: _apply_evidence_indexed,
        EventType.RETRIEVAL_EXECUTED: _apply_retrieval_executed,
        EventType.ENTITY_LINKED: _apply_entity_linked,
        # Sprint 4: Evaluation Layer
        EventType.TRACE_CAPTURED: _apply_trace_captured,
        EventType.EVALUATION_COMPLETED: _apply_evaluation_completed,
        EventType.HALLUCINATION_DETECTED: _apply_hallucination_detected,
        EventType.SYSTEM_FEEDBACK_GENERATED: _apply_system_feedback_generated,
        # Sprint 5: Production Multi-Agent
        EventType.AGENT_ASSIGNED: _apply_agent_assigned,
        EventType.AGENT_COMPLETED: _apply_agent_completed,
        EventType.CACHE_HIT: _apply_cache_hit,
        EventType.CACHE_MISS: _apply_cache_miss,
        EventType.SYSTEM_RETRY: _apply_system_retry,
        EventType.SYSTEM_DEGRADED: _apply_system_degraded,
        # v2 Kernel
        EventType.MEMORY_UPDATED: _apply_memory_updated,
        EventType.TOOL_EXECUTED: _apply_tool_executed,
        EventType.PROCESS_EXECUTED: _apply_process_executed,
        EventType.RULE_EVALUATED: _apply_rule_evaluated,
        EventType.TUNING_APPLIED: _apply_tuning_applied,
    }

    handler = handlers.get(event.event_type)
    if handler:
        handler(state, event)


def _apply_user_query(state: RuntimeState, event: Event) -> None:
    state.query = event.payload.get("query_text", "")
    state.status = "planning"


def _apply_intent_classified(state: RuntimeState, event: Event) -> None:
    state.intent = Intent(
        intent_type=event.payload.get("intent", "unknown"),
        confidence=event.payload.get("confidence", 0.0),
        entities=event.payload.get("entities", []),
        raw_query=state.query or "",
    )


def _apply_plan_created(state: RuntimeState, event: Event) -> None:
    plan_data = event.payload.get("plan", [])
    state.plan = [
        PlanStep(
            step_id=step.get("step_id", i),
            tool_name=step.get("tool_name", "unknown"),
            description=step.get("description", ""),
            input_params=step.get("input_params", {}),
            status=step.get("status", "pending"),
            depends_on=step.get("depends_on", []),
        )
        for i, step in enumerate(plan_data)
    ]
    state.status = "executing"


def _apply_tool_called(state: RuntimeState, event: Event) -> None:
    tool_name = event.payload.get("tool_name", "")
    for step in state.plan:
        if step.tool_name == tool_name and step.status == "pending":
            step.status = "running"
            break


def _apply_evidence_found(state: RuntimeState, event: Event) -> None:
    tool_name = event.payload.get("tool_name", "")
    evidence = event.payload.get("evidence", [])

    state.tool_results.append(
        ToolResult(
            tool_name=tool_name,
            success=True,
            output=event.payload.get("output", {}),
            evidence=evidence,
            duration_ms=event.payload.get("duration_ms", 0.0),
        )
    )

    step_id = event.payload.get("step_id")
    for plan_step in state.plan:
        if step_id is not None:
            if plan_step.step_id == step_id and plan_step.status == "running":
                plan_step.status = "completed"
                break
        elif plan_step.tool_name == tool_name and plan_step.status == "running":
            plan_step.status = "completed"
            break

    if all(s.status == "completed" for s in state.plan):
        state.status = "answering"


def _apply_evidence_selected(state: RuntimeState, event: Event) -> None:
    state.accepted_evidence_ids = list(event.payload.get("accepted_ids", []))
    state.evidence_selection = {
        "accepted_ids": event.payload.get("accepted_ids", []),
        "rejected_ids": event.payload.get("rejected_ids", []),
        "threshold": event.payload.get("threshold", 0.0),
        "snapshot": event.payload.get("snapshot", []),
    }


def _apply_answer_generated(state: RuntimeState, event: Event) -> None:
    state.answer = Answer(
        text=event.payload.get("answer", ""),
        citations=event.payload.get("citations", []),
        confidence=event.payload.get("confidence"),
    )
    state.status = "completed"


# --- Sprint 3: Knowledge Layer Reducers ---

def _apply_chunk_created(state: RuntimeState, event: Event) -> None:
    chunk_info = {
        "document_id": event.payload.get("document_id", ""),
        "chunk_id": event.payload.get("chunk_id", ""),
        "clause": event.payload.get("clause", ""),
    }
    if chunk_info not in state.retrieved_chunks:
        state.retrieved_chunks.append(chunk_info)


def _apply_ontology_expanded(state: RuntimeState, event: Event) -> None:
    expanded = event.payload.get("expanded_entities", [])
    state.ontology_context = list(dict.fromkeys(state.ontology_context + expanded))
    state.retrieval_path.append(f"ontology_expanded({len(expanded)} entities)")


def _apply_evidence_indexed(state: RuntimeState, event: Event) -> None:
    ev_id = event.payload.get("evidence_id", "")
    chunk_id = event.payload.get("chunk_id", "")
    if "nodes" not in state.evidence_graph:
        state.evidence_graph = {"nodes": [], "edges": []}
    if chunk_id not in state.evidence_graph["nodes"]:
        state.evidence_graph["nodes"].append(chunk_id)
    state.evidence_graph.setdefault("edges", []).append(
        {"from": chunk_id, "to": ev_id, "type": "evidence"}
    )


def _apply_retrieval_executed(state: RuntimeState, event: Event) -> None:
    query = event.payload.get("query", "")
    count = event.payload.get("result_count", 0)
    onto = event.payload.get("ontology_used", False)
    state.retrieval_path.append(f"retrieval('{query[:30]}' -> {count} results, onto={onto})")


def _apply_entity_linked(state: RuntimeState, event: Event) -> None:
    entity_id = event.payload.get("entity_id", "")
    evidence_id = event.payload.get("evidence_id", "")
    if "edges" not in state.evidence_graph:
        state.evidence_graph = {"nodes": [], "edges": []}
    state.evidence_graph.setdefault("nodes", [])
    if entity_id not in state.evidence_graph["nodes"]:
        state.evidence_graph["nodes"].append(entity_id)
    state.evidence_graph["edges"].append(
        {"from": evidence_id, "to": entity_id, "type": "linked_to"}
    )


# --- Sprint 4: Evaluation Layer Reducers ---

def _apply_trace_captured(state: RuntimeState, event: Event) -> None:
    state.trace_id = event.payload.get("trace_id", "")

def _apply_evaluation_completed(state: RuntimeState, event: Event) -> None:
    state.evaluation_result = {
        "total_score": event.payload.get("total_score", 0.0),
        "dimensions": event.payload.get("dimensions", {}),
        "diagnosis": event.payload.get("diagnosis", ""),
    }
    state.diagnosis = event.payload.get("diagnosis", "")

def _apply_hallucination_detected(state: RuntimeState, event: Event) -> None:
    state.hallucination_report = {
        "score": event.payload.get("hallucination_score", 0.0),
        "severity": event.payload.get("severity", "NONE"),
        "violations": event.payload.get("violations", []),
    }

def _apply_system_feedback_generated(state: RuntimeState, event: Event) -> None:
    state.feedback_signals = event.payload.get("signals", [])


# --- Sprint 5: Production Multi-Agent Reducers ---

def _apply_agent_assigned(state: RuntimeState, event: Event) -> None:
    agent_name = event.payload.get("agent_name", "")
    state.agent_execution_graph.append({
        "agent": agent_name, "status": "assigned",
        "task": event.payload.get("task", {}),
    })

def _apply_agent_completed(state: RuntimeState, event: Event) -> None:
    agent_name = event.payload.get("agent_name", "")
    state.agent_execution_graph.append({
        "agent": agent_name, "status": "completed",
        "result": event.payload.get("result", {}),
    })

def _apply_cache_hit(state: RuntimeState, event: Event) -> None:
    state.cache_state = {
        "hit": True,
        "store": event.payload.get("store", ""),
        "key": event.payload.get("key", ""),
        "source_trace_id": event.payload.get("source_trace_id", ""),
        "source_session_id": event.payload.get("source_session_id", ""),
        "replay_projection": event.payload.get("replay_projection", False),
        "latency_ms": event.payload.get("latency_ms", 0),
    }

def _apply_cache_miss(state: RuntimeState, event: Event) -> None:
    state.cache_state = {"hit": False, "store": event.payload.get("store", ""),
                         "key": event.payload.get("key", "")}

def _apply_system_retry(state: RuntimeState, event: Event) -> None:
    state.failure_recovery_path.append(
        f"retry:{event.payload.get('component','')}:attempt_{event.payload.get('attempt',0)}"
    )

def _apply_system_degraded(state: RuntimeState, event: Event) -> None:
    state.system_health["degraded"] = True
    state.failure_recovery_path.append(
        f"degraded:{event.payload.get('reason','unknown')}"
    )


# --- v2 Kernel Reducers ---

def _apply_memory_updated(state: RuntimeState, event: Event) -> None:
    action = event.payload.get("action", "")
    facts = event.payload.get("facts", {})
    state.memory_context["last_action"] = action
    if facts:
        state.memory_facts.update(facts)


def _apply_tool_executed(state: RuntimeState, event: Event) -> None:
    tool_name = event.payload.get("tool_name", "")
    state.agent_execution_graph.append({
        "agent": "tool",
        "tool": tool_name,
        "status": event.payload.get("status", ""),
        "duration_ms": event.payload.get("duration_ms", 0.0),
    })


def _apply_process_executed(state: RuntimeState, event: Event) -> None:
    state.process_result = {
        "process_name": event.payload.get("process_name", ""),
        "path": event.payload.get("path", []),
        "terminal_state": event.payload.get("terminal_state", ""),
        "outcome": event.payload.get("outcome", ""),
    }


def _apply_rule_evaluated(state: RuntimeState, event: Event) -> None:
    state.rule_evaluation = {
        "rules_evaluated": event.payload.get("rules_evaluated", 0),
        "rules_matched": event.payload.get("rules_matched", 0),
        "top_decisions": event.payload.get("top_decisions", []),
        "summary": event.payload.get("summary", ""),
    }


def _apply_tuning_applied(state: RuntimeState, event: Event) -> None:
    state.tuning_weights = dict(event.payload.get("weights", {}))


def replay_state(store, session_id: str) -> RuntimeState:
    """Convenience function to replay a session's events and rebuild state."""
    events = store.replay(session_id)
    return reduce(session_id, events)
