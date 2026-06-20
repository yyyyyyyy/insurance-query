"""
Tests for State Reducer (Sprint 1.2).

Covers:
- Reducer is a pure function (same input -> same output)
- State reconstruction from ordered events
- Correct status transitions
- Replay capability
"""

import pytest

from runtime.engine.event_store import (
    EventStore,
    answer_generated_event,
    evidence_found_event,
    intent_classified_event,
    plan_created_event,
    tool_called_event,
    user_query_event,
)
from runtime.engine.reducer import reduce, replay_state
from runtime.engine.state import RuntimeState


class TestReducer:
    """Test the pure reducer function."""

    def test_reduce_empty_events_returns_initial_state(self):
        state = reduce("session-1", [])
        assert isinstance(state, RuntimeState)
        assert state.session_id == "session-1"
        assert state.query is None
        assert state.intent is None
        assert state.plan == []
        assert state.answer is None
        assert state.event_count == 0
        assert state.status == "created"

    def test_reduce_user_query_event(self):
        events = [user_query_event("s1", 1, "重疾险保障什么？")]
        state = reduce("s1", events)
        assert state.query == "重疾险保障什么？"
        assert state.status == "planning"
        assert state.event_count == 1

    def test_reduce_intent_classified_event(self):
        events = [
            user_query_event("s1", 1, "比较百万医疗和重疾险"),
            intent_classified_event("s1", 2, "product_comparison", 0.9,
                                    entities=[{"type": "product", "value": "百万医疗"}]),
        ]
        state = reduce("s1", events)
        assert state.intent is not None
        assert state.intent.intent_type == "product_comparison"
        assert state.intent.confidence == 0.9
        assert len(state.intent.entities) == 1
        assert state.status == "planning"

    def test_reduce_plan_created_event(self):
        plan = [{"step_id": 1, "tool_name": "product_search", "description": "搜索产品"}]
        events = [
            user_query_event("s1", 1, "查询"),
            intent_classified_event("s1", 2, "coverage_question", 0.8),
            plan_created_event("s1", 3, plan=plan),
        ]
        state = reduce("s1", events)
        assert len(state.plan) == 1
        assert state.plan[0].tool_name == "product_search"
        assert state.plan[0].status == "pending"
        assert state.status == "executing"

    def test_reduce_evidence_found_event(self):
        plan = [{"step_id": 1, "tool_name": "product_search", "description": "搜索产品"}]
        events = [
            user_query_event("s1", 1, "query"),
            intent_classified_event("s1", 2, "general_inquiry", 0.7),
            plan_created_event("s1", 3, plan=plan),
            tool_called_event("s1", 4, tool_name="product_search", input_params={}),
            evidence_found_event(
                "s1", 5, tool_name="product_search",
                evidence=[{"source": "catalog", "product_id": "P001"}],
                output={"results": [{"id": "P001"}]}
            ),
        ]
        state = reduce("s1", events)
        assert len(state.tool_results) == 1
        assert state.tool_results[0].tool_name == "product_search"
        assert state.tool_results[0].success is True
        assert len(state.tool_results[0].evidence) == 1
        assert state.plan[0].status == "completed"
        assert state.status == "answering"

    def test_reduce_answer_generated_event(self):
        plan = [{"step_id": 1, "tool_name": "product_search", "description": "搜索产品"}]
        events = [
            user_query_event("s1", 1, "query"),
            intent_classified_event("s1", 2, "general_inquiry", 0.7),
            plan_created_event("s1", 3, plan=plan),
            evidence_found_event("s1", 4, "product_search", evidence=[]),
            answer_generated_event("s1", 5, answer="这是答案",
                                   citations=[{"source": "test"}], confidence=0.85),
        ]
        state = reduce("s1", events)
        assert state.answer is not None
        assert state.answer.text == "这是答案"
        assert len(state.answer.citations) == 1
        assert state.answer.confidence == 0.85
        assert state.status == "completed"

    def test_reducer_is_pure_function(self):
        events = [
            user_query_event("s1", 1, "test query"),
            intent_classified_event("s1", 2, "test_intent", 0.8),
        ]
        state1 = reduce("s1", events)
        state2 = reduce("s1", events)
        assert state1.query == state2.query
        assert state1.intent.intent_type == state2.intent.intent_type
        assert state1.intent.confidence == state2.intent.confidence
        assert state1.status == state2.status

    def test_reducer_is_deterministic(self):
        events = [
            user_query_event("s1", 1, "query"),
            intent_classified_event("s1", 2, "intent", 0.9),
            plan_created_event("s1", 3, plan=[
                {"step_id": 1, "tool_name": "test_tool", "description": "test"}
            ]),
            evidence_found_event("s1", 4, "test_tool", evidence=[]),
            answer_generated_event("s1", 5, "answer", confidence=0.9),
        ]
        state_a = reduce("s1", events)
        state_b = reduce("s1", events)
        assert state_a.to_dict() == state_b.to_dict()


class TestReplayState:
    """Test replay_state convenience function."""

    def test_replay_through_store(self):
        store = EventStore()
        store.append(user_query_event("s1", 1, "test replay"))
        store.append(intent_classified_event("s1", 2, "test_intent", 0.9))
        state = replay_state(store, "s1")
        assert state.query == "test replay"
        assert state.intent.intent_type == "test_intent"

    def test_replay_nonexistent_session(self):
        store = EventStore()
        state = replay_state(store, "nonexistent")
        assert state.event_count == 0


class TestStateSerialization:
    """Test RuntimeState.to_dict()."""

    def test_empty_state_to_dict(self):
        state = RuntimeState(session_id="s1")
        d = state.to_dict()
        assert d["session_id"] == "s1"
        assert d["query"] is None
        assert d["intent"] is None
        assert d["plan"] == []
        assert d["answer"] is None
        assert d["status"] == "created"

    def test_full_state_to_dict(self):
        events = [
            user_query_event("s1", 1, "full state test"),
            intent_classified_event("s1", 2, "test_intent", 0.95),
            plan_created_event("s1", 3, plan=[
                {"step_id": 1, "tool_name": "test_tool", "description": "test"}
            ]),
            evidence_found_event("s1", 4, "test_tool", evidence=[]),
            answer_generated_event("s1", 5, "answer text", confidence=0.9),
        ]
        state = reduce("s1", events)
        d = state.to_dict()
        assert d["query"] == "full state test"
        assert d["intent"]["intent_type"] == "test_intent"
        assert d["intent"]["confidence"] == 0.95
        assert len(d["plan"]) == 1
        assert len(d["tool_results"]) == 1
        assert d["answer"]["text"] == "answer text"
        assert d["status"] == "completed"
