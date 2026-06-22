"""
Tests for the Runtime Engine — MultiAgentEngine (Kernel v2).

Covers exit criteria:
- Accept query
- Generate plan
- Emit events
- Return answer
- Replay state from event log
"""

from runtime.agents.orchestrator import MultiAgentEngine
from runtime.engine.event_store import EventStore
from runtime.engine.reducer import replay_state


class TestEnginePipeline:
    """Test the complete query pipeline."""

    def test_accept_query_and_return_answer(self):
        engine = MultiAgentEngine()
        result = engine.query("重疾险保障什么？")
        assert "answer" in result
        assert result["answer"]["text"] is not None
        assert len(result["answer"]["text"]) > 0

    def test_generate_plan_from_query(self):
        engine = MultiAgentEngine()
        result = engine.query("比较百万医疗和重疾险")
        state = replay_state(engine.event_store, result["session_id"]).to_dict()
        assert len(state["plan"]) > 0
        tool_names = [s["tool_name"] for s in state["plan"]]
        assert "compare" in tool_names

    def test_emit_events(self):
        engine = MultiAgentEngine()
        result = engine.query("查询产品信息")
        trace = result["event_trace"]
        assert len(trace) > 0

        event_types = [e["event_type"] for e in trace]
        assert "USER_QUERY" in event_types
        assert "INTENT_CLASSIFIED" in event_types
        assert "PLAN_CREATED" in event_types
        assert "ANSWER_GENERATED" in event_types

    def test_replay_state_from_event_log(self):
        engine = MultiAgentEngine()
        session_id = engine.query("查询保障范围")["session_id"]

        replayed_state = replay_state(engine.event_store, session_id)
        assert replayed_state is not None
        assert replayed_state.query is not None
        assert replayed_state.answer is not None

    def test_trace_contains_all_event_types(self):
        engine = MultiAgentEngine()
        result = engine.query("e生保一年多少钱？")
        trace = result["event_trace"]

        event_types = {e["event_type"] for e in trace}
        required_types = {
            "USER_QUERY",
            "INTENT_CLASSIFIED",
            "PLAN_CREATED",
            "ANSWER_GENERATED",
            "MEMORY_UPDATED",
            "TUNING_APPLIED",
        }
        assert required_types.issubset(event_types), f"Missing: {required_types - event_types}"

    def test_evidence_is_present_in_answer(self):
        engine = MultiAgentEngine()
        result = engine.query("理赔流程是什么？")
        answer = result["answer"]
        assert "citations" in answer
        assert "evidence_count" in answer
        assert answer["evidence_count"] > 0

    def test_multiple_queries_independent(self):
        engine = MultiAgentEngine()
        r1 = engine.query("查询产品")
        r2 = engine.query("查询法规")

        assert r1["session_id"] != r2["session_id"]
        assert engine.event_store.session_count() == 2

    def test_product_comparison_query(self):
        engine = MultiAgentEngine()
        result = engine.query("e生保和好医保有什么区别？")

        answer = result["answer"]
        assert answer["intent"] == "product_comparison"
        assert "compare" in answer["tools_used"]

    def test_coverage_question_query(self):
        engine = MultiAgentEngine()
        result = engine.query("平安福重疾险保障癌症吗？")

        answer = result["answer"]
        assert answer["intent"] == "coverage_question"
        assert len(answer["tools_used"]) > 0

    def test_regulation_lookup_query(self):
        engine = MultiAgentEngine()
        result = engine.query("健康保险管理办法的规定是什么？")

        answer = result["answer"]
        assert answer["intent"] == "regulation_lookup"
        assert "regulation_search" in answer["tools_used"]

    def test_session_trace_retrieval(self):
        engine = MultiAgentEngine()
        result = engine.query("查询测试")
        session_id = result["session_id"]

        trace = engine.get_session_trace(session_id)
        assert len(trace) > 0
        assert len(trace) == len(result["event_trace"])


class TestEngineWithCustomEventStore:
    """Test engine with a shared/pre-existing event store."""

    def test_shared_event_store(self):
        store = EventStore()
        engine1 = MultiAgentEngine(event_store=store)
        engine2 = MultiAgentEngine(event_store=store)

        engine1.query("查询1")
        engine2.query("查询2")

        assert store.session_count() == 2
        assert store.count() > 4

    def test_replay_across_engines(self):
        store = EventStore()
        engine1 = MultiAgentEngine(event_store=store)
        result = engine1.query("跨引擎测试")
        session_id = result["session_id"]

        engine2 = MultiAgentEngine(event_store=store)
        state = replay_state(engine2.event_store, session_id)
        assert state.query == "跨引擎测试"


class TestAnswerQuality:
    """Test answer quality requirements."""

    def test_answer_has_structured_fields(self):
        engine = MultiAgentEngine()
        result = engine.query("比较产品")

        answer = result["answer"]
        assert "text" in answer
        assert "citations" in answer
        assert "confidence" in answer
        assert "intent" in answer
        assert "tools_used" in answer
        assert "evidence_count" in answer

    def test_confidence_is_reasonable(self):
        engine = MultiAgentEngine()
        result = engine.query("明确的比较查询：e生保和好医保哪个更好？")
        confidence = result["answer"]["confidence"]
        assert 0.0 <= confidence <= 1.0
        assert confidence >= 0.3

    def test_answer_contains_query_text(self):
        engine = MultiAgentEngine()
        result = engine.query("查询重疾险保障")
        assert "重疾险" in result["answer"]["text"] or "查询" in result["answer"]["text"]
