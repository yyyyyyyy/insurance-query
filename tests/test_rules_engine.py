"""Rule engine operator and matching tests."""

from knowledge.rules.engine import RuleEngine, _compare


class TestRuleEngineOperators:
    def test_unknown_operator_returns_false(self):
        assert _compare("hello", "ell", "greater_than") is False

    def test_gte_numeric(self):
        assert _compare(30, 18, "gte") is True
        assert _compare(10, 18, "gte") is False

    def test_rule_with_unknown_operator_not_matched(self):
        rules = [{
            "rule_id": "R-TEST",
            "domain": "underwriting",
            "description": "等待期检查",
            "if": {"conditions": [{
                "field": "eligible",
                "operator": "greater_than",
                "value": True,
            }]},
            "then": {"decision": "reject", "action": "deny"},
            "confidence": "HIGH",
            "source": "test",
            "source_ref": "test",
        }]
        engine = RuleEngine(rules)
        result = engine.evaluate(
            query_text="等待期",
            intent="eligibility_check",
            tool_results={"eligibility_check": {"eligible": True}},
        )
        matched = [d for d in result.decisions if d.matched]
        assert not matched
