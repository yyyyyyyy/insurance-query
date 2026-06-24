"""Closed-loop runtime kernel v3 integration tests (S1–S8)."""

import pytest

from evaluation.feedback.tuner import SelfTuner
from infra.db.session_store import WorkingMemory
from runtime.agents.orchestrator import MultiAgentEngine
from runtime.evidence.canonical import CanonicalEvidenceSet
from runtime.evidence.adapters import tool_evidence_to_candidates
from runtime.evidence.selector import select_evidence_for_answer
from runtime.engine.event_store import evidence_selected_event
from runtime.engine.reducer import reduce


def _last_event(event_trace, event_type: str):
    """Return the latest event of a type (event_trace is cumulative per session)."""
    matches = [e for e in event_trace if e["event_type"] == event_type]
    assert matches, f"missing {event_type} in event trace"
    return matches[-1]


class TestCanonicalEvidenceLifecycle:
    def test_canonical_evidence_lifecycle(self):
        ces = CanonicalEvidenceSet()
        ces.add_candidates(tool_evidence_to_candidates("document_search", [{
            "document_id": "D1",
            "chunk_id": "C1",
            "content": "等待期30日",
            "clause": "2.1",
            "source_type": "policy_clause",
        }]))
        accepted_ids, rejected_ids = select_evidence_for_answer(
            ces, evidence_threshold=0.0, intent="coverage_question",
        )
        assert accepted_ids
        assert ces.accepted_items()
        assert ces.to_evidence_dicts(accepted_only=True)

    def test_evidence_selected_reducer(self):
        ev = evidence_selected_event(
            "s1", 5,
            accepted_ids=["tool:C1"],
            rejected_ids=[],
            threshold=0.1,
            snapshot=[],
        )
        state = reduce("s1", [ev])
        assert state.accepted_evidence_ids == ["tool:C1"]
        assert state.evidence_selection["threshold"] == 0.1


class TestClosedLoopRuntime:
    @pytest.fixture
    def engine(self, tmp_path):
        tuner = SelfTuner(config_path=str(tmp_path / "tuning.json"))
        tuner.config.evidence_threshold = 0.0
        return MultiAgentEngine(tuner=tuner)

    def test_evidence_selected_before_answer(self, engine):
        result = engine.query("重疾险保障范围")
        events = result["event_trace"]
        types = [e["event_type"] for e in events]
        assert "EVIDENCE_SELECTED" in types
        sel_idx = types.index("EVIDENCE_SELECTED")
        ans_idx = types.index("ANSWER_GENERATED")
        assert sel_idx < ans_idx

    def test_hybrid_accepted_in_answer(self, engine):
        result = engine.query("重疾险保障范围")
        sel = next(e for e in result["event_trace"] if e["event_type"] == "EVIDENCE_SELECTED")
        snapshot = sel["payload"].get("snapshot", [])
        hybrid_accepted = [
            s for s in snapshot
            if s.get("source") == "hybrid" and s.get("stage") == "accepted"
        ]
        assert hybrid_accepted, "expected hybrid evidence accepted"
        used = [s for s in hybrid_accepted if s.get("used_in_answer")]
        assert used

    def test_retrieval_decision_trace_present(self, engine):
        result = engine.query("百万医疗险续保条件")
        retr = next(e for e in result["event_trace"] if e["event_type"] == "RETRIEVAL_EXECUTED")
        assert retr["payload"].get("decision_trace")
        assert retr["payload"].get("chunks")

    def test_tool_always_executes_with_retrieval(self, engine):
        result = engine.query("比较e生保和好医保的免赔额")
        events = result["event_trace"]
        tool_exec = [e for e in events if e["event_type"] == "TOOL_EXECUTED"]
        assert len(tool_exec) >= 1
        for e in tool_exec:
            assert "skipped" not in str(e.get("payload", {})).lower()

    def test_process_affects_answer_text(self, engine):
        result = engine.query("理赔流程是什么？需要哪些材料？")
        proc = result.get("process_result") or result["answer"].get("process_result")
        assert proc
        outcome = proc.get("outcome", "")
        assert outcome
        assert outcome in result["answer"]["text"] or "流程" in result["answer"]["text"]

    def test_evaluation_uses_event_store(self, engine):
        result = engine.query("比较e生保和好医保")
        event_types = {e["event_type"] for e in result["event_trace"]}
        assert "RETRIEVAL_EXECUTED" in event_types
        assert "EVIDENCE_SELECTED" in event_types
        assert result["evaluation"].get("total_score", 0) >= 0
        assert "retrieval" in result["evaluation"].get("dimensions", {})

    def test_memory_follow_up_changes_retrieval_and_answer(self, tmp_path):
        wm = WorkingMemory(db_path=str(tmp_path / "cl_mem.db"))
        engine = MultiAgentEngine(working_memory=wm)
        sid = "cl-loop-mem-001"
        r1 = engine.query("e生保的免赔额是多少", session_id=sid)
        r2 = engine.query("它的等待期呢", session_id=sid)

        retr1 = _last_event(r1["event_trace"], "RETRIEVAL_EXECUTED")
        retr2 = _last_event(r2["event_trace"], "RETRIEVAL_EXECUTED")
        assert retr2["payload"].get("query") != retr1["payload"].get("query")
        assert "e生保" in r2.get("resolved_query", "") or "P001" in r2.get("resolved_query", "")

        sel1 = _last_event(r1["event_trace"], "EVIDENCE_SELECTED")
        sel2 = _last_event(r2["event_trace"], "EVIDENCE_SELECTED")
        assert sel1["payload"].get("accepted_ids") != sel2["payload"].get("accepted_ids")

    def test_memory_facts_persist_after_restart(self, tmp_path):
        db = str(tmp_path / "cl_persist.db")
        wm1 = WorkingMemory(db_path=db)
        engine1 = MultiAgentEngine(working_memory=wm1)
        sid = "cl-persist-session"
        engine1.query("比较e生保和好医保", session_id=sid)
        wm1.add_facts(sid, {"test_fact": {"key": "test_fact", "value": "ok"}})

        wm2 = WorkingMemory(db_path=db)
        ctx = wm2.get_or_create(sid)
        assert "test_fact" in ctx.facts

    def test_tuner_weights_change_retrieval_trace(self, tmp_path):
        tuning_path = str(tmp_path / "cl_tuner_a.json")
        tuner_a = SelfTuner(config_path=tuning_path)
        tuner_a.config.bm25_weight = 0.85
        tuner_a.config.vector_weight = 0.10
        tuner_a.config.ontology_weight = 0.05
        tuner_a._save_config()

        engine_a = MultiAgentEngine(tuner=tuner_a)
        r1 = engine_a.query("百万医疗险续保条件", session_id="tuner-a")

        tuner_b = SelfTuner(config_path=str(tmp_path / "cl_tuner_b.json"))
        tuner_b.config.bm25_weight = 0.10
        tuner_b.config.vector_weight = 0.85
        tuner_b.config.ontology_weight = 0.05
        tuner_b._save_config()

        engine_b = MultiAgentEngine(tuner=tuner_b)
        r2 = engine_b.query("百万医疗险续保条件", session_id="tuner-b")

        dt1 = next(e for e in r1["event_trace"] if e["event_type"] == "RETRIEVAL_EXECUTED")
        dt2 = next(e for e in r2["event_trace"] if e["event_type"] == "RETRIEVAL_EXECUTED")
        trace1 = dt1["payload"].get("decision_trace", [])
        trace2 = dt2["payload"].get("decision_trace", [])
        assert trace1 and trace2
        fc1 = trace1[0].get("feature_contribution", {})
        fc2 = trace2[0].get("feature_contribution", {})
        assert fc1.get("weights") != fc2.get("weights")

        sel1 = next(e for e in r1["event_trace"] if e["event_type"] == "EVIDENCE_SELECTED")
        _sel2 = next(e for e in r2["event_trace"] if e["event_type"] == "EVIDENCE_SELECTED")
        # accepted set may differ when ranking changes
        assert sel1["payload"].get("accepted_ids") is not None

    def test_cache_hit_integrates_event_store(self):
        engine = MultiAgentEngine()
        q = "cache-i1-integration-test"
        sid = "cache-i1-session"
        r1 = engine.query(q, session_id=sid)
        assert r1.get("cached") is not True
        assert "CACHE_MISS" in {e["event_type"] for e in r1["event_trace"]}

        r2 = engine.query(q, session_id=sid)
        assert r2.get("cached") is True
        types = [e["event_type"] for e in r2["event_trace"]]
        assert "CACHE_HIT" in types
        assert "USER_QUERY" in types
        assert "ANSWER_GENERATED" in types
        assert "TRACE_CAPTURED" in types
        hit = next(e for e in r2["event_trace"] if e["event_type"] == "CACHE_HIT")
        assert hit["payload"].get("source_trace_id")
        assert hit["payload"].get("replay_projection") is True
        # New turn trace_id; causal link to source execution
        assert r2["trace_id"] != r1["trace_id"]
        assert r2["cache_hit"]["source_trace_id"] == r1["trace_id"]
