"""Pipeline integration: event order and stage wiring."""

import pytest

from runtime.agents.orchestrator import MultiAgentEngine
from evaluation.feedback.tuner import SelfTuner


class TestPipelineIntegration:
    @pytest.fixture
    def engine(self, tmp_path):
        tuner = SelfTuner(config_path=str(tmp_path / "tuning.json"))
        tuner.config.evidence_threshold = 0.0
        return MultiAgentEngine(tuner=tuner)

    def test_event_order_unchanged(self, engine):
        result = engine.query("重疾险保障范围")
        types = [e["event_type"] for e in result["event_trace"]]
        assert types.index("EVIDENCE_SELECTED") < types.index("ANSWER_GENERATED")
        assert "RETRIEVAL_EXECUTED" in types
        assert "TOOL_EXECUTED" in types
        assert "EVALUATION_COMPLETED" in types
        assert "TUNING_APPLIED" in types

    def test_observability_metrics_recorded(self, engine):
        result = engine.query("e生保免赔额")
        assert "observability" in result
        assert result["observability"]["queries"]["total"] >= 1
