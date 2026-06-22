"""
Event System — Append-only Event Sourcing for InsureQuery Runtime.

ARCHITECTURE RULE #3: All state is event-sourced. No hidden state allowed.
"""

from __future__ import annotations

import uuid
from abc import ABC
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class EventType(str, Enum):
    """Canonical event types for the insurance reasoning runtime."""

    USER_QUERY = "USER_QUERY"
    INTENT_CLASSIFIED = "INTENT_CLASSIFIED"
    PLAN_CREATED = "PLAN_CREATED"
    TOOL_CALLED = "TOOL_CALLED"
    EVIDENCE_FOUND = "EVIDENCE_FOUND"
    EVIDENCE_SELECTED = "EVIDENCE_SELECTED"
    ANSWER_GENERATED = "ANSWER_GENERATED"
    # Sprint 3: Knowledge Layer events
    CHUNK_CREATED = "CHUNK_CREATED"
    EMBEDDING_GENERATED = "EMBEDDING_GENERATED"
    ENTITY_LINKED = "ENTITY_LINKED"
    ONTOLOGY_EXPANDED = "ONTOLOGY_EXPANDED"
    EVIDENCE_INDEXED = "EVIDENCE_INDEXED"
    RETRIEVAL_EXECUTED = "RETRIEVAL_EXECUTED"
    # Sprint 4: Evaluation Layer events
    TRACE_CAPTURED = "TRACE_CAPTURED"
    EVALUATION_COMPLETED = "EVALUATION_COMPLETED"
    HALLUCINATION_DETECTED = "HALLUCINATION_DETECTED"
    SYSTEM_FEEDBACK_GENERATED = "SYSTEM_FEEDBACK_GENERATED"
    # Sprint 5: Production Multi-Agent events
    AGENT_ASSIGNED = "AGENT_ASSIGNED"
    AGENT_COMPLETED = "AGENT_COMPLETED"
    CACHE_HIT = "CACHE_HIT"
    CACHE_MISS = "CACHE_MISS"
    SYSTEM_RETRY = "SYSTEM_RETRY"
    SYSTEM_DEGRADED = "SYSTEM_DEGRADED"
    # v2 Kernel events
    MEMORY_UPDATED = "MEMORY_UPDATED"
    TOOL_EXECUTED = "TOOL_EXECUTED"
    PROCESS_EXECUTED = "PROCESS_EXECUTED"
    RULE_EVALUATED = "RULE_EVALUATED"
    TUNING_APPLIED = "TUNING_APPLIED"


class Event(ABC):
    """Immutable event base class.

    Every event carries:
    - event_id: globally unique identifier
    - event_type: discriminant for reducer dispatch
    - timestamp: UTC wall-clock time of occurrence
    - sequence_number: monotonically increasing ordinal within a session
    - session_id: groups events belonging to a single user query
    - payload: event-type-specific data
    """

    def __init__(
        self,
        event_type: EventType,
        session_id: str,
        sequence_number: int,
        payload: Dict[str, Any],
        event_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ):
        self.event_id = event_id or str(uuid.uuid4())
        self.event_type = event_type
        self.session_id = session_id
        self.sequence_number = sequence_number
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.payload = payload

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "session_id": self.session_id,
            "sequence_number": self.sequence_number,
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        return cls(
            event_type=EventType(data["event_type"]),
            session_id=data["session_id"],
            sequence_number=data["sequence_number"],
            payload=data["payload"],
            event_id=data.get("event_id"),
            timestamp=datetime.fromisoformat(data["timestamp"])
            if isinstance(data["timestamp"], str)
            else data["timestamp"],
        )

    def __repr__(self) -> str:
        return f"<Event {self.event_type.value} seq={self.sequence_number} session={self.session_id[:8]}>"


# --- Factory helpers for each event type ---


def user_query_event(
    session_id: str, sequence_number: int, query_text: str, **kwargs
) -> Event:
    """Create a USER_QUERY event."""
    return Event(
        event_type=EventType.USER_QUERY,
        session_id=session_id,
        sequence_number=sequence_number,
        payload={"query_text": query_text, **kwargs},
    )


def intent_classified_event(
    session_id: str,
    sequence_number: int,
    intent: str,
    confidence: float,
    entities: Optional[List[Dict[str, Any]]] = None,
    **kwargs,
) -> Event:
    """Create an INTENT_CLASSIFIED event."""
    return Event(
        event_type=EventType.INTENT_CLASSIFIED,
        session_id=session_id,
        sequence_number=sequence_number,
        payload={
            "intent": intent,
            "confidence": confidence,
            "entities": entities or [],
            **kwargs,
        },
    )


def plan_created_event(
    session_id: str,
    sequence_number: int,
    plan: List[Dict[str, Any]],
    reasoning: Optional[str] = None,
    **kwargs,
) -> Event:
    """Create a PLAN_CREATED event."""
    return Event(
        event_type=EventType.PLAN_CREATED,
        session_id=session_id,
        sequence_number=sequence_number,
        payload={"plan": plan, "reasoning": reasoning, **kwargs},
    )


def tool_called_event(
    session_id: str,
    sequence_number: int,
    tool_name: str,
    input_params: Dict[str, Any],
    **kwargs,
) -> Event:
    """Create a TOOL_CALLED event."""
    return Event(
        event_type=EventType.TOOL_CALLED,
        session_id=session_id,
        sequence_number=sequence_number,
        payload={"tool_name": tool_name, "input_params": input_params, **kwargs},
    )


def evidence_found_event(
    session_id: str,
    sequence_number: int,
    tool_name: str,
    evidence: List[Dict[str, Any]],
    source: Optional[str] = None,
    **kwargs,
) -> Event:
    """Create an EVIDENCE_FOUND event."""
    return Event(
        event_type=EventType.EVIDENCE_FOUND,
        session_id=session_id,
        sequence_number=sequence_number,
        payload={
            "tool_name": tool_name,
            "evidence": evidence,
            "source": source,
            **kwargs,
        },
    )


def evidence_selected_event(
    session_id: str,
    sequence_number: int,
    accepted_ids: List[str],
    rejected_ids: List[str],
    threshold: float,
    snapshot: Optional[List[Dict[str, Any]]] = None,
    **kwargs,
) -> Event:
    """Create an EVIDENCE_SELECTED event (candidate → accepted gate)."""
    return Event(
        event_type=EventType.EVIDENCE_SELECTED,
        session_id=session_id,
        sequence_number=sequence_number,
        payload={
            "accepted_ids": accepted_ids,
            "rejected_ids": rejected_ids,
            "threshold": threshold,
            "snapshot": snapshot or [],
            **kwargs,
        },
    )


def answer_generated_event(
    session_id: str,
    sequence_number: int,
    answer: str,
    citations: Optional[List[Dict[str, Any]]] = None,
    confidence: Optional[float] = None,
    **kwargs,
) -> Event:
    """Create an ANSWER_GENERATED event."""
    return Event(
        event_type=EventType.ANSWER_GENERATED,
        session_id=session_id,
        sequence_number=sequence_number,
        payload={
            "answer": answer,
            "citations": citations or [],
            "confidence": confidence,
            **kwargs,
        },
    )


# --- Sprint 3: Knowledge Layer Event Factories ---

def chunk_created_event(session_id: str, sequence_number: int,
                        document_id: str, chunk_id: str, clause: str = "",
                        **kwargs) -> Event:
    return Event(EventType.CHUNK_CREATED, session_id, sequence_number,
                 payload={"document_id": document_id, "chunk_id": chunk_id,
                          "clause": clause, **kwargs})


def embedding_generated_event(session_id: str, sequence_number: int,
                              chunk_id: str, dim: int, **kwargs) -> Event:
    return Event(EventType.EMBEDDING_GENERATED, session_id, sequence_number,
                 payload={"chunk_id": chunk_id, "dim": dim, **kwargs})


def entity_linked_event(session_id: str, sequence_number: int,
                        entity_id: str, evidence_id: str, **kwargs) -> Event:
    return Event(EventType.ENTITY_LINKED, session_id, sequence_number,
                 payload={"entity_id": entity_id, "evidence_id": evidence_id, **kwargs})


def ontology_expanded_event(session_id: str, sequence_number: int,
                            seed_entities: List[str], expanded_entities: List[str],
                            **kwargs) -> Event:
    return Event(EventType.ONTOLOGY_EXPANDED, session_id, sequence_number,
                 payload={"seed_entities": seed_entities,
                          "expanded_entities": expanded_entities, **kwargs})


def evidence_indexed_event(session_id: str, sequence_number: int,
                           evidence_id: str, chunk_id: str, **kwargs) -> Event:
    return Event(EventType.EVIDENCE_INDEXED, session_id, sequence_number,
                 payload={"evidence_id": evidence_id, "chunk_id": chunk_id, **kwargs})


def retrieval_executed_event(session_id: str, sequence_number: int,
                             query: str, result_count: int,
                             ontology_used: bool = False, **kwargs) -> Event:
    return Event(EventType.RETRIEVAL_EXECUTED, session_id, sequence_number,
                 payload={"query": query, "result_count": result_count,
                          "ontology_used": ontology_used, **kwargs})


# --- Sprint 4: Evaluation Layer Event Factories ---

def trace_captured_event(session_id: str, sequence_number: int,
                         trace_id: str, **kwargs) -> Event:
    return Event(EventType.TRACE_CAPTURED, session_id, sequence_number,
                 payload={"trace_id": trace_id, **kwargs})

def evaluation_completed_event(session_id: str, sequence_number: int,
                               total_score: float, dimensions: Dict[str, Any],
                               **kwargs) -> Event:
    return Event(EventType.EVALUATION_COMPLETED, session_id, sequence_number,
                 payload={"total_score": total_score, "dimensions": dimensions, **kwargs})

def hallucination_detected_event(session_id: str, sequence_number: int,
                                 hallucination_score: float, severity: str,
                                 violations: List[Dict[str, Any]], **kwargs) -> Event:
    return Event(EventType.HALLUCINATION_DETECTED, session_id, sequence_number,
                 payload={"hallucination_score": hallucination_score,
                          "severity": severity, "violations": violations, **kwargs})

def system_feedback_generated_event(session_id: str, sequence_number: int,
                                    signals: List[Dict[str, Any]], **kwargs) -> Event:
    return Event(EventType.SYSTEM_FEEDBACK_GENERATED, session_id, sequence_number,
                 payload={"signals": signals, **kwargs})


# --- Sprint 5: Production Multi-Agent Event Factories ---

def agent_assigned_event(session_id: str, sequence_number: int,
                         agent_name: str, task: Dict[str, Any], **kwargs) -> Event:
    return Event(EventType.AGENT_ASSIGNED, session_id, sequence_number,
                 payload={"agent_name": agent_name, "task": task, **kwargs})

def agent_completed_event(session_id: str, sequence_number: int,
                          agent_name: str, result: Dict[str, Any], **kwargs) -> Event:
    return Event(EventType.AGENT_COMPLETED, session_id, sequence_number,
                 payload={"agent_name": agent_name, "result": result, **kwargs})

def cache_hit_event(session_id: str, sequence_number: int,
                    store: str, key: str, **kwargs) -> Event:
    return Event(EventType.CACHE_HIT, session_id, sequence_number,
                 payload={"store": store, "key": key, **kwargs})

def cache_miss_event(session_id: str, sequence_number: int,
                     store: str, key: str, **kwargs) -> Event:
    return Event(EventType.CACHE_MISS, session_id, sequence_number,
                 payload={"store": store, "key": key, **kwargs})

def system_retry_event(session_id: str, sequence_number: int,
                       component: str, attempt: int, **kwargs) -> Event:
    return Event(EventType.SYSTEM_RETRY, session_id, sequence_number,
                 payload={"component": component, "attempt": attempt, **kwargs})

def system_degraded_event(session_id: str, sequence_number: int,
                          reason: str, **kwargs) -> Event:
    return Event(EventType.SYSTEM_DEGRADED, session_id, sequence_number,
                 payload={"reason": reason, **kwargs})


# --- v2 Kernel Event Factories ---

def memory_updated_event(
    session_id: str,
    sequence_number: int,
    action: str,
    facts: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Event:
    return Event(
        EventType.MEMORY_UPDATED,
        session_id,
        sequence_number,
        payload={"action": action, "facts": facts or {}, **kwargs},
    )


def tool_executed_event(
    session_id: str,
    sequence_number: int,
    tool_name: str,
    status: str,
    duration_ms: float = 0.0,
    fact_keys: Optional[List[str]] = None,
    **kwargs,
) -> Event:
    return Event(
        EventType.TOOL_EXECUTED,
        session_id,
        sequence_number,
        payload={
            "tool_name": tool_name,
            "status": status,
            "duration_ms": duration_ms,
            "fact_keys": fact_keys or [],
            **kwargs,
        },
    )


def process_executed_event(
    session_id: str,
    sequence_number: int,
    process_name: str,
    path: List[str],
    terminal_state: str,
    outcome: str = "",
    **kwargs,
) -> Event:
    return Event(
        EventType.PROCESS_EXECUTED,
        session_id,
        sequence_number,
        payload={
            "process_name": process_name,
            "path": path,
            "terminal_state": terminal_state,
            "outcome": outcome,
            **kwargs,
        },
    )


def rule_evaluated_event(
    session_id: str,
    sequence_number: int,
    rules_evaluated: int,
    rules_matched: int,
    top_decisions: Optional[List[Dict[str, Any]]] = None,
    summary: str = "",
    **kwargs,
) -> Event:
    return Event(
        EventType.RULE_EVALUATED,
        session_id,
        sequence_number,
        payload={
            "rules_evaluated": rules_evaluated,
            "rules_matched": rules_matched,
            "top_decisions": top_decisions or [],
            "summary": summary,
            **kwargs,
        },
    )


def tuning_applied_event(
    session_id: str,
    sequence_number: int,
    weights: Dict[str, float],
    reason: str = "",
    **kwargs,
) -> Event:
    return Event(
        EventType.TUNING_APPLIED,
        session_id,
        sequence_number,
        payload={"weights": weights, "reason": reason, **kwargs},
    )


# --- Append-only Event Store ---


class EventStore:
    """Append-only event log.

    ARCHITECTURE RULE #3: No mutations, no deletions. Events are immutable.
    State is reconstructed by replaying events through the reducer.
    """

    def __init__(self):
        self._events: List[Event] = []
        self._session_index: Dict[str, List[int]] = {}  # session_id -> list of indices

    def append(self, event: Event) -> Event:
        """Append an event to the log. Returns the stored event (immutable)."""
        idx = len(self._events)
        self._events.append(event)

        if event.session_id not in self._session_index:
            self._session_index[event.session_id] = []
        self._session_index[event.session_id].append(idx)

        return event

    def get_session_events(self, session_id: str) -> List[Event]:
        """Retrieve all events for a given session in insertion order."""
        indices = self._session_index.get(session_id, [])
        return [self._events[i] for i in indices]

    def get_all_events(self) -> List[Event]:
        """Return a copy of all events."""
        return list(self._events)

    def get_event_by_id(self, event_id: str) -> Optional[Event]:
        for event in self._events:
            if event.event_id == event_id:
                return event
        return None

    def count(self) -> int:
        return len(self._events)

    def session_count(self) -> int:
        return len(self._session_index)

    def list_sessions(self) -> List[str]:
        """Return all session IDs with events."""
        return list(self._session_index.keys())

    def clear(self) -> None:
        """Clear all events. Use with caution — primarily for testing."""
        self._events.clear()
        self._session_index.clear()

    def replay(self, session_id: str) -> List[Event]:
        """Replay all events for a session (used by reducer to rebuild state)."""
        return self.get_session_events(session_id)

    # -- Batch transaction protocol (optional for subclasses) --
    # Default no-op implementations so the orchestrator can call these
    # unconditionally; persistent stores (SqliteEventStore) override them
    # to group many appends into a single commit.

    def begin_batch(self) -> None:
        """Begin a batch transaction. No-op for in-memory stores."""
        return None

    def commit_batch(self) -> None:
        """Commit a pending batch transaction. No-op for in-memory stores."""
        return None

    def rollback_batch(self) -> None:
        """Roll back a pending batch transaction. No-op for in-memory stores."""
        return None
