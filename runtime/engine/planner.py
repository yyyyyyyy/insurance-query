"""
Intent Classifier and Planner for InsureQuery Runtime.

In Sprint 1, this uses rule-based classification and plan generation.
Sprint 2+ will integrate with LLM-based planning while maintaining the
same interface contract.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Tuple

# --- Intent Classification ---

INTENT_PATTERNS: List[Tuple[str, str, List[str]]] = [
    (
        "product_comparison",
        r"(比较|对比|区别|差异|哪个更好|哪个更划算|选哪个|vs)",
        ["product", "plan"],
    ),
    (
        "coverage_question",
        r"(保障|覆盖|赔付|报销|包含|是否.*保|能.*赔|有.*保障)",
        ["coverage", "disease", "treatment"],
    ),
    (
        "regulation_lookup",
        r"(监管|规定|法规|政策|合规|银保监|必须.*条款)",
        ["regulation", "rule"],
    ),
    (
        "price_inquiry",
        r"(价格|费用|保费|多少钱|成本|费率|多少钱一年)",
        ["product", "price"],
    ),
    (
        "claim_process",
        r"(理赔|报案|索赔|出险|怎么赔|理赔流程|索赔流程)",
        ["claim", "process"],
    ),
    (
        "eligibility_check",
        r"(能不能买|可以买吗|符合条件|资格|投保条件|年龄.*限制|还能买|还能.*保|可以.*买|能.*投保)",
        ["product", "eligibility", "age", "health"],
    ),
]

KNOWN_ENTITIES = {
    "product": [
        "百万医疗", "重疾险", "医疗险", "意外险", "寿险", "年金险",
        "e生保", "平安福", "国寿福", "好医保", "微医保",
    ],
    "disease": [
        "癌症", "心脏病", "糖尿病", "高血压", "脑中风", "冠心病",
    ],
    "coverage": [
        "住院医疗", "门诊", "手术", "特殊门诊", "重疾", "轻症", "中症",
    ],
    "regulation": [
        "健康保险管理办法", "保险法", "重疾定义", "偿付能力",
    ],
}


def _product_entity_values() -> List[str]:
    """Static product keywords plus names from PRODUCT_CATALOG."""
    seen = set(KNOWN_ENTITIES.get("product", []))
    values = list(seen)
    try:
        from runtime.tools.data import PRODUCT_CATALOG
        for prod in PRODUCT_CATALOG:
            for key in ("name", "company_short", "product_type"):
                val = (prod.get(key) or "").strip()
                if val and val not in seen:
                    seen.add(val)
                    values.append(val)
    except Exception:
        pass
    return values


def _extract_entities(query_text: str, entity_types: List[str]) -> List[Dict[str, Any]]:
    """Extract known entities from query text."""
    entities = []
    for entity_type in entity_types:
        if entity_type == "product":
            for value in _product_entity_values():
                if value in query_text:
                    entities.append({
                        "type": entity_type,
                        "value": value,
                        "source": "keyword_match",
                    })
            continue
        if entity_type in KNOWN_ENTITIES:
            for value in KNOWN_ENTITIES[entity_type]:
                if value in query_text:
                    entities.append({
                        "type": entity_type,
                        "value": value,
                        "source": "keyword_match",
                    })
    return entities


def classify_intent(query_text: str) -> Dict[str, Any]:
    """Classify user intent from query text using pattern matching.

    Returns a dict with intent_type, confidence, and extracted entities.
    """
    best_match = None
    best_score = 0.0

    for intent_type, pattern, entity_types in INTENT_PATTERNS:
        matches = re.findall(pattern, query_text, re.IGNORECASE)
        if matches:
            score = min(len(matches) * 0.3 + 0.4, 0.95)
            if score > best_score:
                best_score = score
                best_match = (intent_type, entity_types)

    if best_match is None:
        return {"intent": "general_inquiry", "confidence": 0.5, "entities": []}

    intent_type, entity_types = best_match
    entities = _extract_entities(query_text, entity_types)

    return {"intent": intent_type, "confidence": round(best_score, 2), "entities": entities}


# --- Plan Generation ---

PLAN_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    "product_comparison": [
        {"step_id": 1, "tool_name": "entity_lookup", "description": "识别比较的产品实体",
         "input_params": {"entity_type": "Product"}},
        {"step_id": 2, "tool_name": "attribute_extraction", "description": "提取产品核心属性",
         "input_params": {"attributes": ["coverage_limit", "premium", "exclusions"],
                          "product_ids": []}},
        {"step_id": 3, "tool_name": "compare", "description": "结构化对比产品",
         "input_params": {"product_ids": [],
                          "dimensions": ["waiting_period", "deductible", "coverage_limit", "guaranteed_renewal"]}},
    ],
    "coverage_question": [
        {"step_id": 1, "tool_name": "product_search", "description": "搜索相关保险产品",
         "input_params": {"top_k": 5}},
        {"step_id": 2, "tool_name": "document_search", "description": "检索保障条款文档",
         "input_params": {"document_type": "policy_clause", "top_k": 3}},
        {"step_id": 3, "tool_name": "attribute_extraction", "description": "提取保障范围和限制",
         "input_params": {"attributes": ["coverage_limit", "critical_illness_limit", "outpatient_limit", "exclusions"],
                          "product_ids": []}},
    ],
    "regulation_lookup": [
        {"step_id": 1, "tool_name": "regulation_search", "description": "检索相关法规",
         "input_params": {"top_k": 5}},
        {"step_id": 2, "tool_name": "document_search", "description": "检索监管文件原文",
         "input_params": {"document_type": "regulation", "top_k": 3}},
        {"step_id": 3, "tool_name": "relation_traversal", "description": "遍历法规关联关系",
         "input_params": {"entity_id": "ENT-P001", "relation_type": "regulated_by"}},
    ],
    "price_inquiry": [
        {"step_id": 1, "tool_name": "product_search", "description": "搜索产品信息",
         "input_params": {"top_k": 5}},
        {"step_id": 2, "tool_name": "attribute_extraction", "description": "提取价格和费率信息",
         "input_params": {"attributes": ["premium", "premium_reference"],
                          "product_ids": []}},
    ],
    "claim_process": [
        {"step_id": 1, "tool_name": "document_search", "description": "检索理赔流程文档",
         "input_params": {"document_type": "claim_procedure", "top_k": 3}},
        {"step_id": 2, "tool_name": "entity_lookup", "description": "查找相关产品理赔规则",
         "input_params": {"entity_type": "Product"}},
    ],
    "eligibility_check": [
        {"step_id": 1, "tool_name": "product_search", "description": "搜索符合条件的产品",
         "input_params": {"top_k": 5}},
        {"step_id": 2, "tool_name": "eligibility_check", "description": "检查投保资格",
         "input_params": {"product_id": "", "age": None}},
    ],
    "general_inquiry": [
        {"step_id": 1, "tool_name": "product_search", "description": "搜索相关信息",
         "input_params": {"top_k": 5}},
        {"step_id": 2, "tool_name": "document_search", "description": "检索相关文档",
         "input_params": {"document_type": "", "top_k": 3}},
    ],
}


def generate_plan(query_text: str, intent_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate an execution plan based on intent classification.

    In Sprint 1, uses template-based plan generation.
    Sprint 2+ will support LLM-based dynamic planning.
    """
    intent_type = intent_result.get("intent", "general_inquiry")
    template = PLAN_TEMPLATES.get(intent_type, PLAN_TEMPLATES["general_inquiry"])
    # Deep copy so PlannerAgent mutations to input_params never leak into PLAN_TEMPLATES.
    return copy.deepcopy(template)
