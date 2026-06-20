"""
Runtime Engine — Core orchestrator, Sprint 2 (Real Tool Execution).

ARCHITECTURE:
    UserQuery -> Intent -> Plan -> ToolDispatcher -> Real Tools -> Evidence -> Answer

SPRINT 2 CHANGE: Replaced mock execute_tool() with ToolDispatcher + ToolRegistry.
All tools are now real deterministic implementations per 06-Tool-Contracts.md.

DEPRECATED: This engine has been superseded by MultiAgentEngine
(runtime/agents/orchestrator.py). Use MultiAgentEngine for all new code.
InsureQueryEngine will be removed in a future version.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from runtime.engine.event_store import (
    EventStore,
    answer_generated_event,
    evidence_found_event,
    intent_classified_event,
    plan_created_event,
    tool_called_event,
    user_query_event,
)
from runtime.llm.plugin import classify_intent_auto, compose_answer_auto, generate_plan_auto
from runtime.engine.reducer import replay_state
from runtime.engine.state import RuntimeState
from runtime.tools.base import ToolResult
from runtime.tools.registry import ToolDispatcher, create_default_registry


class InsureQueryEngine:
    """Core runtime engine for insurance query processing.

    SPRINT 2: Uses ToolDispatcher with real tools instead of mock execute_tool().
    """

    def __init__(self, event_store: Optional[EventStore] = None,
                 dispatcher: Optional[ToolDispatcher] = None):
        import warnings
        warnings.warn("InsureQueryEngine is deprecated, use MultiAgentEngine instead", DeprecationWarning, stacklevel=2)
        self.event_store = event_store or EventStore()
        self.dispatcher = dispatcher or ToolDispatcher(create_default_registry())

    def query(self, query_text: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        session_id = session_id or str(uuid.uuid4())
        seq = 0

        seq += 1
        self.event_store.append(user_query_event(session_id, seq, query_text))

        intent_result = classify_intent_auto(query_text)
        seq += 1
        self.event_store.append(intent_classified_event(
            session_id, seq, intent=intent_result["intent"],
            confidence=intent_result["confidence"], entities=intent_result["entities"],
        ))

        plan = generate_plan_auto(query_text, intent_result)
        seq += 1
        self.event_store.append(plan_created_event(
            session_id, seq, plan=plan,
            reasoning=f"Template-based plan for intent: {intent_result['intent']}",
        ))

        all_evidence: List[Dict[str, Any]] = []
        tool_outputs: Dict[str, Any] = {}

        for step in plan:
            tool_name = step["tool_name"]
            params = step.get("input_params", {})
            if "query" not in params:
                params["query"] = query_text

            seq += 1
            self.event_store.append(tool_called_event(
                session_id, seq, tool_name=tool_name, input_params=params,
            ))

            result: ToolResult = self.dispatcher.dispatch(tool_name, params)

            if result.success:
                tool_outputs[tool_name] = result.data
                evidence_dicts = [e.to_dict() for e in result.evidence]
                all_evidence.extend(evidence_dicts)

                seq += 1
                self.event_store.append(evidence_found_event(
                    session_id, seq, tool_name=tool_name,
                    evidence=evidence_dicts, output=result.data,
                    duration_ms=result.duration_ms,
                ))

        answer = self._generate_answer(query_text, intent_result, plan, tool_outputs, all_evidence)

        seq += 1
        self.event_store.append(answer_generated_event(
            session_id, seq, answer=answer["text"],
            citations=answer.get("citations", []),
            confidence=answer.get("confidence"),
        ))

        state = replay_state(self.event_store, session_id)

        return {
            "session_id": session_id,
            "answer": answer,
            "trace": [e.to_dict() for e in self.event_store.get_session_events(session_id)],
            "state": state.to_dict(),
        }

    def _generate_answer(self, query_text, intent_result, plan, tool_outputs, evidence):
        intent_type = intent_result["intent"]
        citations = _format_citations(evidence)
        answer_text = compose_answer_auto(query_text, intent_type, tool_outputs, evidence)
        return {
            "text": answer_text, "citations": citations,
            "confidence": _compute_confidence(intent_result, evidence),
            "intent": intent_type,
            "tools_used": [s["tool_name"] for s in plan],
            "evidence_count": len(evidence),
        }

    def replay_session(self, session_id: str) -> RuntimeState:
        return replay_state(self.event_store, session_id)

    def get_session_trace(self, session_id: str) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self.event_store.get_session_events(session_id)]


# Deprecated: _compose_answer, _format_citations, _compute_confidence are now in runtime.llm.answer.
# Kept here for backward compatibility — import from runtime.llm.answer for new code.
from runtime.llm.answer import _format_citations, _compute_confidence  # noqa: F811

def _compose_answer(query_text, intent_type, tool_outputs, evidence):
    """Deprecated: use runtime.llm.answer._template_answer directly."""
    import warnings
    warnings.warn("_compose_answer is deprecated, use _template_answer in runtime.llm.answer", DeprecationWarning, stacklevel=2)
    from runtime.llm.answer import _template_answer
    return _template_answer(query_text, intent_type, tool_outputs, evidence)
