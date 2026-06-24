"""
Tests for Planner (Sprint 1.3 — Intent Classification + Plan Generation).
"""


from runtime.engine.planner import classify_intent, generate_plan, INTENT_PATTERNS, PLAN_TEMPLATES


class TestIntentClassification:
    """Test rule-based intent classification."""

    def test_product_comparison_intent(self):
        result = classify_intent("百万医疗险和重疾险有什么区别？")
        assert result["intent"] == "product_comparison"
        assert result["confidence"] > 0.5

    def test_coverage_question_intent(self):
        result = classify_intent("重疾险保障哪些疾病？")
        assert result["intent"] == "coverage_question"
        assert result["confidence"] > 0.5

    def test_regulation_lookup_intent(self):
        result = classify_intent("健康保险管理办法对百万医疗有什么规定？")
        assert result["intent"] == "regulation_lookup"
        assert result["confidence"] > 0.5

    def test_price_inquiry_intent(self):
        result = classify_intent("e生保一年多少钱？")
        assert result["intent"] == "price_inquiry"
        assert result["confidence"] > 0.5

    def test_claim_process_intent(self):
        result = classify_intent("出险后怎么理赔？")
        assert result["intent"] == "claim_process"

    def test_eligibility_intent(self):
        result = classify_intent("60岁还能买医疗险吗？")
        assert result["intent"] == "eligibility_check"

    def test_general_inquiry_fallback(self):
        result = classify_intent("你好")
        assert result["intent"] == "general_inquiry"
        assert result["confidence"] == 0.5

    def test_entity_extraction_product(self):
        result = classify_intent("e生保和平安福哪个更好？")
        entities = result["entities"]
        product_names = [e["value"] for e in entities if e["type"] == "product"]
        assert "e生保" in product_names or "平安福" in product_names

    def test_entity_extraction_disease(self):
        result = classify_intent("重疾险保障癌症和心脏病吗？")
        entities = result["entities"]
        disease_names = [e["value"] for e in entities if e["type"] == "disease"]
        assert "癌症" in disease_names or "心脏病" in disease_names

    def test_confidence_is_between_0_and_1(self):
        queries = [
            "比较重疾险和医疗险",
            "保障哪些疾病",
            "价格多少",
            "你好",
        ]
        for q in queries:
            result = classify_intent(q)
            assert 0 <= result["confidence"] <= 1.0, f"Confidence out of range for: {q}"

    def test_all_intent_patterns_covered(self):
        all_intents = {p[0] for p in INTENT_PATTERNS}
        for intent in all_intents:
            assert intent in PLAN_TEMPLATES, f"Missing plan template for intent: {intent}"


class TestPlanGeneration:
    """Test template-based plan generation."""

    def test_product_comparison_plan(self):
        intent = {"intent": "product_comparison", "confidence": 0.9, "entities": []}
        plan = generate_plan("比较产品", intent)
        assert len(plan) >= 3
        tool_names = [s["tool_name"] for s in plan]
        assert "compare" in tool_names

    def test_coverage_question_plan(self):
        intent = {"intent": "coverage_question", "confidence": 0.8, "entities": []}
        plan = generate_plan("保障什么", intent)
        tool_names = [s["tool_name"] for s in plan]
        assert "product_search" in tool_names
        assert "document_search" in tool_names

    def test_regulation_lookup_plan(self):
        intent = {"intent": "regulation_lookup", "confidence": 0.9, "entities": []}
        plan = generate_plan("法规查询", intent)
        tool_names = [s["tool_name"] for s in plan]
        assert "regulation_search" in tool_names
        assert "relation_traversal" in tool_names

    def test_all_plans_have_step_ids(self):
        for intent_type in PLAN_TEMPLATES:
            intent = {"intent": intent_type, "confidence": 0.8, "entities": []}
            plan = generate_plan("test", intent)
            for step in plan:
                assert "step_id" in step, f"Missing step_id in {intent_type}"
                assert "tool_name" in step, f"Missing tool_name in {intent_type}"
                assert "description" in step, f"Missing description in {intent_type}"

    def test_plan_is_a_copy_not_reference(self):
        intent = {"intent": "product_comparison", "confidence": 0.9, "entities": []}
        plan1 = generate_plan("test", intent)
        plan2 = generate_plan("test", intent)
        plan1[0]["description"] = "modified"
        assert plan2[0]["description"] != "modified", "Plan should be a deep copy, not a reference"

    def test_plan_input_params_do_not_mutate_template(self):
        intent = {"intent": "product_comparison", "confidence": 0.9, "entities": []}
        plan = generate_plan("test", intent)
        original_ids = list(PLAN_TEMPLATES["product_comparison"][2]["input_params"]["product_ids"])
        plan[2]["input_params"]["product_ids"] = ["P999", "P998"]
        assert PLAN_TEMPLATES["product_comparison"][2]["input_params"]["product_ids"] == original_ids
