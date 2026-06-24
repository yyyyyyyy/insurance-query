"""
Tests for the Event System (Sprint 1.1).

Covers:
- Event creation via factory helpers
- Event serialization/deserialization
- EventStore append-only behavior
- EventStore session indexing
- EventStore replay
"""


from runtime.engine.event_store import (
    EventStore,
    EventType,
    answer_generated_event,
    evidence_found_event,
    intent_classified_event,
    plan_created_event,
    tool_called_event,
    user_query_event,
)


class TestEventCreation:
    """Test that factory helpers produce correctly-typed events."""

    def test_user_query_event(self):
        event = user_query_event("session-1", 1, "百万医疗险和重疾险有什么区别？")
        assert event.event_type == EventType.USER_QUERY
        assert event.session_id == "session-1"
        assert event.sequence_number == 1
        assert event.payload["query_text"] == "百万医疗险和重疾险有什么区别？"
        assert event.event_id

    def test_intent_classified_event(self):
        event = intent_classified_event(
            "session-1", 2, intent="product_comparison", confidence=0.85,
            entities=[{"type": "product", "value": "百万医疗"}]
        )
        assert event.event_type == EventType.INTENT_CLASSIFIED
        assert event.payload["intent"] == "product_comparison"
        assert event.payload["confidence"] == 0.85
        assert len(event.payload["entities"]) == 1

    def test_plan_created_event(self):
        plan = [
            {"step_id": 1, "tool_name": "entity_lookup", "description": "识别产品"}
        ]
        event = plan_created_event("session-1", 3, plan=plan, reasoning="template")
        assert event.event_type == EventType.PLAN_CREATED
        assert len(event.payload["plan"]) == 1
        assert event.payload["plan"][0]["tool_name"] == "entity_lookup"

    def test_tool_called_event(self):
        event = tool_called_event(
            "session-1", 4, tool_name="product_search",
            input_params={"query": "重疾险", "top_k": 5}
        )
        assert event.event_type == EventType.TOOL_CALLED
        assert event.payload["tool_name"] == "product_search"
        assert event.payload["input_params"]["top_k"] == 5

    def test_evidence_found_event(self):
        evidence = [{"source": "doc_001", "text": "保单条款..."}]
        event = evidence_found_event(
            "session-1", 5, tool_name="document_search",
            evidence=evidence, source="document_store"
        )
        assert event.event_type == EventType.EVIDENCE_FOUND
        assert len(event.payload["evidence"]) == 1
        assert event.payload["evidence"][0]["source"] == "doc_001"

    def test_answer_generated_event(self):
        event = answer_generated_event(
            "session-1", 6, answer="重疾险与医疗险的核心区别在于...",
            citations=[{"source": "product_catalog", "reference": "P001"}],
            confidence=0.9
        )
        assert event.event_type == EventType.ANSWER_GENERATED
        assert "重疾险" in event.payload["answer"]
        assert len(event.payload["citations"]) == 1
        assert event.payload["confidence"] == 0.9


class TestEventSerialization:
    """Test event to_dict/from_dict round-trip."""

    def test_round_trip(self):
        original = user_query_event("session-1", 1, "测试查询")
        data = original.to_dict()
        restored = original.__class__.from_dict(data)

        assert restored.event_type == original.event_type
        assert restored.session_id == original.session_id
        assert restored.sequence_number == original.sequence_number
        assert restored.payload == original.payload
        assert restored.event_id == original.event_id

    def test_to_dict_structure(self):
        event = user_query_event("s1", 1, "hello")
        data = event.to_dict()

        assert "event_id" in data
        assert "event_type" in data
        assert "session_id" in data
        assert "sequence_number" in data
        assert "timestamp" in data
        assert "payload" in data
        assert data["event_type"] == "USER_QUERY"


class TestEventStore:
    """Test the append-only EventStore."""

    def test_append_single_event(self):
        store = EventStore()
        event = user_query_event("s1", 1, "test")
        store.append(event)
        assert store.count() == 1
        assert store.session_count() == 1

    def test_append_multiple_sessions(self):
        store = EventStore()
        store.append(user_query_event("s1", 1, "query 1"))
        store.append(user_query_event("s2", 1, "query 2"))
        store.append(user_query_event("s1", 2, "query 1 continued"))

        assert store.count() == 3
        assert store.session_count() == 2

    def test_get_session_events_ordering(self):
        store = EventStore()
        store.append(user_query_event("s1", 1, "first"))
        store.append(user_query_event("s2", 1, "other"))
        store.append(intent_classified_event("s1", 2, "test_intent", 0.9))

        s1_events = store.get_session_events("s1")
        assert len(s1_events) == 2
        assert s1_events[0].sequence_number == 1
        assert s1_events[1].sequence_number == 2
        assert s1_events[1].event_type == EventType.INTENT_CLASSIFIED

    def test_get_nonexistent_session(self):
        store = EventStore()
        assert store.get_session_events("nonexistent") == []

    def test_replay_returns_session_events(self):
        store = EventStore()
        store.append(user_query_event("s1", 1, "hello"))
        store.append(intent_classified_event("s1", 2, "test", 0.8))

        events = store.replay("s1")
        assert len(events) == 2
        assert events[0].payload["query_text"] == "hello"

    def test_get_event_by_id(self):
        store = EventStore()
        event = user_query_event("s1", 1, "find me")
        store.append(event)

        found = store.get_event_by_id(event.event_id)
        assert found is not None
        assert found.payload["query_text"] == "find me"

        not_found = store.get_event_by_id("nonexistent-id")
        assert not_found is None

    def test_clear_empties_store(self):
        store = EventStore()
        store.append(user_query_event("s1", 1, "test"))
        store.clear(_testing_only=True)
        assert store.count() == 0
        assert store.session_count() == 0

    def test_get_all_events_returns_copy(self):
        store = EventStore()
        store.append(user_query_event("s1", 1, "one"))
        store.append(user_query_event("s2", 1, "two"))

        all_events = store.get_all_events()
        assert len(all_events) == 2
        all_events.pop()
        assert store.count() == 2
