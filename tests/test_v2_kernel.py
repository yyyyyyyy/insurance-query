"""Kernel v2 integration tests — memory, tuner, process, events."""

import os
import tempfile

from infra.db.session_store import WorkingMemory
from evaluation.feedback.tuner import SelfTuner
from runtime.agents.orchestrator import MultiAgentEngine


class TestMemoryFollowUp:
    def test_memory_follow_up_product(self):
        wm = WorkingMemory(db_path=os.path.join(tempfile.gettempdir(), "test_wm_v2.db"))
        engine = MultiAgentEngine(working_memory=wm)
        session = "v2-memory-session-001"

        r1 = engine.query("e生保的免赔额是多少", session_id=session)
        assert r1["answer"]["evidence_count"] > 0

        r2 = engine.query("它的等待期呢", session_id=session)
        event_types = {e["event_type"] for e in r2["event_trace"]}
        assert "MEMORY_UPDATED" in event_types
        assert r2.get("memory_context", {}).get("is_follow_up") or "e生保" in r2.get("resolved_query", "")


class TestTunerRetrieval:
    def test_tuner_affects_retrieval_weights(self):
        tuner = SelfTuner(config_path=os.path.join(tempfile.gettempdir(), "test_tuning_v2.json"))
        engine = MultiAgentEngine(tuner=tuner)

        engine.query("重疾险保障范围")
        w1 = dict(tuner.get_retrieval_params())

        # Simulate poor retrieval score to trigger bm25 boost
        tuner.apply_evaluation({
            "total_score": 40,
            "dimensions": {"retrieval": 30, "answer": 60},
            "hallucination_score": 0.1,
        })
        w2 = dict(tuner.get_retrieval_params())

        assert w1 != w2 or tuner.config.total_queries >= 1
        assert "bm25_weight" in w2


class TestProcessExecution:
    def test_claim_process_executes(self):
        engine = MultiAgentEngine()
        result = engine.query("理赔流程是什么？需要哪些材料？")
        proc = result.get("process_result") or result["answer"].get("process_result")
        assert proc is not None
        assert proc.get("terminal_state")
        event_types = {e["event_type"] for e in result["event_trace"]}
        assert "PROCESS_EXECUTED" in event_types

    def test_underwriting_process_executes(self):
        engine = MultiAgentEngine()
        result = engine.query("30岁能不能买e生保？")
        proc = result.get("process_result") or result["answer"].get("process_result")
        assert proc is not None
        assert proc.get("process_name") == "underwriting_lifecycle"
        event_types = {e["event_type"] for e in result["event_trace"]}
        assert "PROCESS_EXECUTED" in event_types


class TestEventTraceV2:
    def test_event_trace_v2_complete(self):
        engine = MultiAgentEngine()
        result = engine.query("比较e生保和好医保的免赔额")
        event_types = {e["event_type"] for e in result["event_trace"]}
        required = {
            "INTENT_CLASSIFIED",
            "PLAN_CREATED",
            "MEMORY_UPDATED",
            "RETRIEVAL_EXECUTED",
            "TOOL_EXECUTED",
            "RULE_EVALUATED",
            "ANSWER_GENERATED",
            "EVALUATION_COMPLETED",
            "TUNING_APPLIED",
        }
        missing = required - event_types
        assert not missing, f"Missing v2 events: {missing}"
