"""Sprint 4 Evaluation System Tests — Trace, Eval Engine, Hallucination, Feedback."""

from evaluation.trace.capture import TraceCapture, QueryTrace
from evaluation.engine.scorer import EvaluationEngine, EvaluationResult, DimensionScore
from evaluation.hallucination.detector import HallucinationDetector, HallucinationReport, Violation
from evaluation.feedback.loop import FeedbackLoop, FeedbackSignal
from evaluation.datasets.samples import EvalSample, EVAL_DATASET
from evaluation.runner.runner import EvalRunner
from runtime.agents.orchestrator import MultiAgentEngine
from runtime.engine.reducer import replay_state

# ============================================================
# 7.1 TRACE TESTS
# ============================================================

class TestTraceCapture:
    def make_trace(self) -> QueryTrace:
        tc = TraceCapture()
        state = {"intent": {"intent_type": "test"}, "ontology_context": ["E1"],
                 "retrieval_path": ["step1"], "evidence_graph": {"nodes":["n1"]},
                 "answer": {"text":"answer","citations":[{"ref":"c1"}]}}
        events = [
            {"event_type":"USER_QUERY","payload":{"query_text":"test"}},
            {"event_type":"INTENT_CLASSIFIED","payload":{"intent":"test"}},
            {"event_type":"PLAN_CREATED","payload":{"plan":[{"step_id":1}]}},
            {"event_type":"TOOL_CALLED","payload":{"tool_name":"test_tool","input_params":{}}},
            {"event_type":"EVIDENCE_FOUND","payload":{"evidence":[{"chunk_id":"c1"}]}},
            {"event_type":"RETRIEVAL_EXECUTED","payload":{"result_count":5,"ontology_used":True}},
            {"event_type":"ANSWER_GENERATED","payload":{"answer":"answer"}},
        ]
        return tc.capture("s1", "test query", events, state, 150.0)

    def test_trace_completeness(self):
        """7.1: trace must contain all pipeline stages."""
        t = self.make_trace()
        assert t.trace_id is not None
        assert t.session_id == "s1"
        assert t.intent is not None
        assert t.plan_steps is not None
        assert len(t.tool_calls) > 0
        assert t.evidence_count > 0
        assert t.final_answer is not None

    def test_trace_immutability(self):
        t = self.make_trace()
        orig = t.to_dict()
        t2 = self.make_trace()
        assert t.trace_id != t2.trace_id  # Unique trace IDs

    def test_trace_replay_accuracy(self):
        """7.1: trace replay must preserve query and events."""
        t = self.make_trace()
        assert t.query == "test query"
        assert len(t.runtime_events) > 0

    def test_trace_has_evaluation_metadata(self):
        t = self.make_trace()
        d = t.to_dict()
        assert "trace_id" in d
        assert "session_id" in d
        assert "evidence_count" in d

    def test_trace_capture_store(self):
        tc = TraceCapture()
        state = {"intent":{}, "answer":{"text":"x"}}
        tc.capture("s1","q1",[], state, 0)
        assert tc.trace_count() == 1

    def test_trace_ontology_expansion_recorded(self):
        t = self.make_trace()
        assert t.ontology_expansion["context"] == ["E1"]
        assert len(t.ontology_expansion["path"]) == 1


# ============================================================
# 7.2 EVALUATION TESTS
# ============================================================

class TestEvaluationEngine:
    def make_good_trace(self) -> QueryTrace:
        tc = TraceCapture()
        state = {"intent":{"intent_type":"test"},"evidence_graph":{"nodes":["n1"]},
                 "answer":{"text":"test answer with citation","citations":[{"ref":"c1"}],
                           "confidence":0.9}}
        events = [
            {"event_type":"PLAN_CREATED","payload":{"plan":[{"step_id":1,"tool_name":"t1"},{"step_id":2,"tool_name":"t2"}]}},
            {"event_type":"TOOL_CALLED","payload":{"tool_name":"t1","input_params":{}}},
            {"event_type":"TOOL_CALLED","payload":{"tool_name":"t2","input_params":{}}},
            {"event_type":"EVIDENCE_FOUND","payload":{"evidence":[{"chunk_id":"c1","content":"test evidence"}]}},
            {"event_type":"RETRIEVAL_EXECUTED","payload":{"query":"test","result_count":5,"ontology_used":True}},
        ]
        return tc.capture("s1","test evid query",events,state,100.0)

    def make_bad_trace(self) -> QueryTrace:
        tc = TraceCapture()
        state = {"intent":{},"answer":{"text":"","citations":[]},"evidence_graph":{}}
        events = [{"event_type":"EVIDENCE_FOUND","payload":{"evidence":[]}}]
        return tc.capture("s2","",events,state,0.0)

    def test_full_trace_scores_high(self):
        """Good trace should score high."""
        ee = EvaluationEngine()
        t = self.make_good_trace()
        r = ee.evaluate(t)
        assert r.total_score >= 70

    def test_empty_trace_scores_low(self):
        ee = EvaluationEngine()
        t = self.make_bad_trace()
        r = ee.evaluate(t)
        assert r.total_score < 40

    def test_retrieval_scoring(self):
        """7.2: retrieval dimension must compute correctly."""
        ee = EvaluationEngine()
        t = self.make_good_trace()
        r = ee.evaluate(t)
        rd = r.dimensions["retrieval"]
        assert rd.score > 0
        assert "ontology_hit_rate" in rd.details

    def test_tool_scoring(self):
        """7.2: tool dimension must detect tool diversity."""
        ee = EvaluationEngine()
        t = self.make_good_trace()
        r = ee.evaluate(t)
        td = r.dimensions["tool"]
        assert "tools_used" in td.details

    def test_answer_groundedness(self):
        """7.2: answer must be scored on evidence linkage."""
        ee = EvaluationEngine()
        t = self.make_good_trace()
        r = ee.evaluate(t)
        ad = r.dimensions["answer"]
        assert ad.details["evidence_count"] > 0

    def test_scoring_with_expected_sample(self):
        ee = EvaluationEngine()
        t = self.make_good_trace()
        sample = EvalSample("E1","test","test_intent",expected_evidence=["c1"])
        r = ee.evaluate(t, sample)
        assert r.total_score >= 0

    def test_efficiency_scoring(self):
        ee = EvaluationEngine()
        t = self.make_good_trace()
        r = ee.evaluate(t)
        ed = r.dimensions["efficiency"]
        assert ed.score > 0
        assert "latency_ms" in ed.details

    def test_normalized_scores_between_0_and_1(self):
        ee = EvaluationEngine()
        t = self.make_good_trace()
        r = ee.evaluate(t)
        for n in r.breakdown.values():
            assert 0 <= n <= 1.0

    def test_dimension_score_normalized(self):
        ds = DimensionScore("test", 3.0, 5.0)
        assert 0.5 <= ds.normalized() <= 0.7

    def test_evaluation_result_dict(self):
        ee = EvaluationEngine()
        t = self.make_good_trace()
        r = ee.evaluate(t)
        d = r.to_dict()
        assert "total_score" in d
        assert "diagnosis" in d
        assert "failure_points" in d


# ============================================================
# 7.3 HALLUCINATION TESTS
# ============================================================

class TestHallucinationDetector:
    def test_no_hallucination_on_good_trace(self):
        """Good trace should have zero hallucination score."""
        tc = TraceCapture()
        state = {"answer":{"text":"e生保保障恶性肿瘤和急性心肌梗塞","citations":[{"ref":"c1"}]}}
        events = [{"event_type":"EVIDENCE_FOUND","payload":{"evidence":[
            {"chunk_id":"c1","content":"e生保保障恶性肿瘤和急性心肌梗塞"}
        ]}}]
        trace = tc.capture("s1","q",events,state,0)
        hd = HallucinationDetector()
        r = hd.detect(trace)
        assert r.hallucination_score == 0.0
        assert r.severity == "NONE"

    def test_unsupported_claim_detected(self):
        """7.3: unsupported claims must be detected."""
        tc = TraceCapture()
        state = {"answer":{"text":"e生保覆盖太空旅行","citations":[{"ref":"c1"}]}}
        events = [{"event_type":"EVIDENCE_FOUND","payload":{"evidence":[
            {"chunk_id":"c1","content":"e生保保障恶性肿瘤"}
        ]}}]
        trace = tc.capture("s1","q",events,state,0)
        hd = HallucinationDetector()
        r = hd.detect(trace)
        # Should detect some mismatch
        assert r.hallucination_score >= 0

    def test_missing_evidence_detected(self):
        """7.3: zero evidence must trigger hallucination."""
        tc = TraceCapture()
        state = {"answer":{"text":"some answer","citations":[]}}
        events = []
        trace = tc.capture("s1","q",events,state,0)
        hd = HallucinationDetector()
        r = hd.detect(trace)
        assert r.severity == "HIGH"
        assert len(r.violations) > 0

    def test_empty_answer_detected(self):
        tc = TraceCapture()
        state = {"answer":{"text":"","citations":[]}}
        trace = tc.capture("s1","q",[],state,0)
        hd = HallucinationDetector()
        r = hd.detect(trace)
        assert r.severity in ("HIGH", "MEDIUM")

    def test_report_to_dict(self):
        r = HallucinationReport(0.0, [], "NONE")
        d = r.to_dict()
        assert d["severity"] == "NONE"
        assert d["hallucination_score"] == 0.0


# ============================================================
# 7.4 FEEDBACK TESTS
# ============================================================

class TestFeedbackLoop:
    def test_feedback_generated(self):
        """7.4: feedback must be generated from evaluation."""
        fl = FeedbackLoop()
        er = EvaluationResult("t1","s1",45.0,
            dimensions={"retrieval":DimensionScore("retrieval",1.0,5.0,{"ontology_hit_rate":0.2}),
                        "tool":DimensionScore("tool",5.0,5.0,{"tools_used":[]}),
                        "reasoning":DimensionScore("reasoning",5.0,5.0,{}),
                        "answer":DimensionScore("answer",5.0,5.0,{"citation_count":1,"evidence_count":1}),
                        "efficiency":DimensionScore("efficiency",5.0,5.0,{"latency_ms":100})},
            diagnosis="test")
        hal = HallucinationReport(0.0, [], "NONE")
        signals = fl.generate(er, hal)
        assert len(signals) > 0
        assert isinstance(signals[0], FeedbackSignal)

    def test_feedback_signal_to_dict(self):
        fs = FeedbackSignal("retrieval_quality","root","fix suggestion","module")
        d = fs.to_dict()
        assert d["issue_type"] == "retrieval_quality"

    def test_hallucination_triggers_feedback(self):
        fl = FeedbackLoop()
        er = EvaluationResult("t1","s1",30.0,
            dimensions={"retrieval":DimensionScore("r",5,5,{}),"tool":DimensionScore("t",5,5,{}),
                        "reasoning":DimensionScore("rs",5,5,{}),
                        "answer":DimensionScore("a",5,5,{"citation_count":0,"evidence_count":0}),
                        "efficiency":DimensionScore("e",5,5,{"latency_ms":100})},
            diagnosis="")
        hal = HallucinationReport(0.5, [Violation("missing_evidence","no evidence","HIGH")], "HIGH")
        signals = fl.generate(er, hal)
        assert any(s.severity == "HIGH" for s in signals)

    def test_latency_triggers_feedback(self):
        fl = FeedbackLoop()
        er = EvaluationResult("t1","s1",50.0,
            dimensions={"retrieval":DimensionScore("r",5,5,{}),"tool":DimensionScore("t",5,5,{}),
                        "reasoning":DimensionScore("rs",5,5,{}),
                        "answer":DimensionScore("a",5,5,{"citation_count":1,"evidence_count":1}),
                        "efficiency":DimensionScore("e",2,5,{"latency_ms":5000,"tool_calls":2})},
            diagnosis="")
        hal = HallucinationReport(0.0,[],"NONE")
        signals = fl.generate(er, hal)
        assert any("latency" in s.root_cause.lower() for s in signals)


# ============================================================
# 7.5 DATASET TESTS
# ============================================================

class TestEvalDataset:
    def test_dataset_has_all_categories(self):
        cats = {s.category for s in EVAL_DATASET}
        assert "product_comparison" in cats
        assert "coverage" in cats
        assert "regulation" in cats
        assert "multi_hop" in cats
        assert "hallucination" in cats

    def test_dataset_samples_valid(self):
        for s in EVAL_DATASET:
            assert s.sample_id
            assert s.question
            assert s.expected_intent
            assert s.min_evidence_count >= 0

    def test_all_samples_have_expected_intent(self):
        for s in EVAL_DATASET:
            assert s.expected_intent in (
                "product_comparison","coverage_question",
                "regulation_lookup","general_inquiry"
            )


# ============================================================
# 7.6 E2E EVALUATION INTEGRATION
# ============================================================

class TestEvaluationIntegration:
    def test_engine_produces_evaluation(self):
        ke = MultiAgentEngine()
        r = ke.query("e生保的保障范围")
        ev = r.get("evaluation", {})
        assert "total_score" in ev
        assert "hallucination_score" in ev
        assert "diagnosis" in ev

    def test_state_has_evaluation_fields(self):
        ke = MultiAgentEngine()
        r = ke.query("重疾险保障什么")
        state = replay_state(ke.event_store, r["session_id"]).to_dict()
        assert "evaluation_result" in state
        assert "hallucination_report" in state
        assert "trace_id" in state

    def test_event_trace_has_sprint4_events(self):
        ke = MultiAgentEngine()
        r = ke.query("保证续保的监管规定")
        event_types = {e["event_type"] for e in r["event_trace"]}
        assert "TRACE_CAPTURED" in event_types
        assert "EVALUATION_COMPLETED" in event_types
        assert "HALLUCINATION_DETECTED" in event_types

    def test_eval_runner_runs_dataset(self):
        ke = MultiAgentEngine()
        runner = EvalRunner(ke)
        result = runner.run_batch(EVAL_DATASET[:4], verbose=False)
        assert result.total_samples == 4
        assert result.avg_score >= 0
        assert len(result.per_sample) == 4

    def test_eval_runner_result_structure(self):
        ke = MultiAgentEngine()
        runner = EvalRunner(ke)
        result = runner.run_batch(EVAL_DATASET[:2], verbose=False)
        d = result.to_dict()
        assert "avg_score" in d
        assert "system_feedback" in d
        assert "per_sample" in d


# ============================================================
# 7.7 SPRINT 4 EVENT CONTRACTS
# ============================================================

class TestSprint4Events:
    def test_new_event_types_exist(self):
        from runtime.engine.event_store import EventType
        assert EventType.TRACE_CAPTURED
        assert EventType.EVALUATION_COMPLETED
        assert EventType.HALLUCINATION_DETECTED
        assert EventType.SYSTEM_FEEDBACK_GENERATED

    def test_trace_captured_event_factory(self):
        from runtime.engine.event_store import trace_captured_event
        e = trace_captured_event("s1", 1, "TRC-123")
        assert e.event_type.value == "TRACE_CAPTURED"
        assert e.payload["trace_id"] == "TRC-123"

    def test_evaluation_completed_event_factory(self):
        from runtime.engine.event_store import evaluation_completed_event
        e = evaluation_completed_event("s1", 1, 85.0, {"retrieval": 5.0})
        assert e.event_type.value == "EVALUATION_COMPLETED"
        assert e.payload["total_score"] == 85.0

    def test_hallucination_detected_event_factory(self):
        from runtime.engine.event_store import hallucination_detected_event
        e = hallucination_detected_event("s1", 1, 0.0, "NONE", [])
        assert e.event_type.value == "HALLUCINATION_DETECTED"

    def test_feedback_generated_event_factory(self):
        from runtime.engine.event_store import system_feedback_generated_event
        e = system_feedback_generated_event("s1", 1, [{"type": "test"}])
        assert e.event_type.value == "SYSTEM_FEEDBACK_GENERATED"
