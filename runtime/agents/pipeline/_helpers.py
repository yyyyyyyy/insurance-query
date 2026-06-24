"""Shared helpers for pipeline stages."""

from __future__ import annotations

import uuid
from typing import Any, Dict, TYPE_CHECKING

from runtime.agents.bus import AgentMessage, AgentContext, AgentStatus
from runtime.engine.event_store import (
    EventStore,
    agent_assigned_event,
    agent_completed_event,
    system_degraded_event,
)

if TYPE_CHECKING:
    from runtime.agents.orchestrator import MultiAgentEngine


class EventSequencer:
    """Monotonic per-session event sequence allocator."""

    def __init__(self, event_store: EventStore, session_id: str):
        self._store = event_store
        self._session_id = session_id
        events = event_store.get_session_events(session_id)
        self._next = (max(e.sequence_number for e in events) + 1) if events else 1

    def append(self, factory, *args, **kwargs) -> None:
        seq = self._next
        self._next += 1
        self._store.append(factory(self._session_id, seq, *args, **kwargs))


def send_agent(
    engine: "MultiAgentEngine",
    ctx: AgentContext,
    seq: EventSequencer,
    recipient: str,
    msg_type: str,
    payload: Dict[str, Any],
    trace_id: str,
    *,
    emit_events: bool = True,
) -> AgentMessage:
    if emit_events:
        seq.append(agent_assigned_event, recipient, {"msg_type": msg_type})

    resp = engine.bus.send(AgentMessage(
        str(uuid.uuid4()), "orchestrator", recipient, msg_type,
        payload, trace_id=trace_id,
    ), ctx)

    agent = engine.bus.get_agent(recipient)
    turn_status = ctx.agent_statuses.get(recipient) if ctx else None
    if turn_status is None and agent:
        turn_status = agent.status

    if emit_events and agent and turn_status is not None:
        status_val = (
            turn_status.value
            if isinstance(turn_status, AgentStatus)
            else str(turn_status)
        )
        seq.append(
            agent_completed_event,
            recipient,
            {"msg_type": resp.msg_type, "status": status_val},
        )
        if turn_status == AgentStatus.FAILED:
            ctx.degraded_mode = True
            seq.append(system_degraded_event, reason=f"agent:{recipient}:failed")

    return resp
