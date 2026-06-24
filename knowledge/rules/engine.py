"""
Rule Engine — Evaluates decision rules against query context and tool outputs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from runtime.config.intent_domains import INTENT_DOMAIN_MAP

logger = logging.getLogger(__name__)


@dataclass
class RuleDecision:
    rule_id: str
    domain: str
    description: str
    decision: str
    action: str
    confidence: str
    source: str
    source_ref: str
    matched: bool = False
    match_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "domain": self.domain,
            "description": self.description,
            "decision": self.decision,
            "action": self.action,
            "confidence": self.confidence,
            "source": self.source,
            "source_ref": self.source_ref,
            "matched": self.matched,
            "match_reason": self.match_reason,
        }


@dataclass
class RuleEvaluation:
    intent: str
    rules_evaluated: int
    rules_matched: int
    decisions: List[RuleDecision] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "rules_evaluated": self.rules_evaluated,
            "rules_matched": self.rules_matched,
            "decisions": [d.to_dict() for d in self.decisions],
            "summary": self.summary,
        }

    def get_decisions_by_type(self, decision_type: str) -> List[RuleDecision]:
        return [d for d in self.decisions if d.decision == decision_type]

    @property
    def has_critical(self) -> bool:
        return any(d.decision == "reject" and d.confidence == "HIGH" for d in self.decisions)


class RuleEngine:
    DECISION_SEVERITY = {
        "reject": 4,
        "exclusion": 3,
        "extra_premium": 2,
        "standard_accept": 1,
        "approve": 0,
        "eligible": 0,
        "partial": 1,
    }

    def __init__(self, rules: Optional[List[Dict[str, Any]]] = None):
        if rules is not None:
            self._rules = rules
        else:
            self._rules = self._load_rules()
        logger.info("RuleEngine initialized with %d rules", len(self._rules))

    @staticmethod
    def _load_rules() -> List[Dict[str, Any]]:
        try:
            from runtime.tools.data_loader import load_rules
            return load_rules()
        except Exception:
            return []

    def evaluate(
        self,
        query_text: str = "",
        intent: str = "general_inquiry",
        tool_results: Optional[Dict[str, Any]] = None,
        evidence: Optional[List[Dict[str, Any]]] = None,
        max_rules: int = 10,
    ) -> RuleEvaluation:
        tool_results = tool_results or {}
        evidence = evidence or []
        candidate_rules = self._filter_by_intent(intent)
        matched_decisions: List[RuleDecision] = []
        for rule in candidate_rules:
            matched_decisions.append(
                self._evaluate_rule(rule, query_text, tool_results, evidence)
            )
        matched_decisions.sort(
            key=lambda d: (
                not d.matched,
                -self.DECISION_SEVERITY.get(d.decision, 0),
                {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(d.confidence, 0),
            )
        )
        matched_decisions = matched_decisions[:max_rules]
        matched_count = sum(1 for d in matched_decisions if d.matched)
        summary = self._generate_summary(intent, matched_decisions, matched_count)
        return RuleEvaluation(
            intent=intent,
            rules_evaluated=len(candidate_rules),
            rules_matched=matched_count,
            decisions=matched_decisions,
            summary=summary,
        )

    def _filter_by_intent(self, intent: str) -> List[Dict[str, Any]]:
        domains = INTENT_DOMAIN_MAP.get(intent, [])
        if intent == "regulation_lookup":
            return [r for r in self._rules if r.get("source") == "regulatory_document"]
        if domains:
            return [r for r in self._rules if r.get("domain") in domains]
        return list(self._rules)

    def _evaluate_rule(
        self,
        rule: Dict[str, Any],
        query_text: str,
        tool_results: Dict[str, Any],
        evidence: List[Dict[str, Any]],
    ) -> RuleDecision:
        conditions = rule.get("if", {}).get("conditions", [])
        then_block = rule.get("then", {})
        description = rule.get("description", "")
        match_reasons: List[str] = []
        tool_match = False
        if conditions:
            for cond in conditions:
                field_name = cond.get("field", "")
                if _check_condition(cond, tool_results, evidence):
                    match_reasons.append(f"condition_matched: {field_name}")
                    tool_match = True
            if not tool_match:
                return RuleDecision(
                    rule_id=rule.get("rule_id", ""),
                    domain=rule.get("domain", ""),
                    description=description,
                    decision=then_block.get("decision", ""),
                    action=then_block.get("action", ""),
                    confidence=rule.get("confidence", "MEDIUM"),
                    source=rule.get("source", ""),
                    source_ref=rule.get("source_ref", ""),
                    matched=False,
                    match_reason="conditions not satisfied",
                )

        keywords = self._extract_keywords(description)
        query_match = any(kw in query_text for kw in keywords if len(kw) >= 2)
        evidence_match = False
        if not conditions:
            for ev in evidence[:10]:
                ev_content = ev.get("content", "")
                if any(kw in ev_content for kw in keywords if len(kw) >= 2):
                    evidence_match = True
                    break

        matched = tool_match or query_match or evidence_match
        if matched:
            reason = " | ".join(match_reasons) if match_reasons else (
                "keyword match in query" if query_match else
                "evidence content match" if evidence_match else
                "rule applicable to intent"
            )
        else:
            reason = "rule not triggered by current query context"

        return RuleDecision(
            rule_id=rule.get("rule_id", ""),
            domain=rule.get("domain", ""),
            description=description,
            decision=then_block.get("decision", ""),
            action=then_block.get("action", ""),
            confidence=rule.get("confidence", "MEDIUM"),
            source=rule.get("source", ""),
            source_ref=rule.get("source_ref", ""),
            matched=matched,
            match_reason=reason,
        )

    @staticmethod
    def _extract_keywords(description: str) -> List[str]:
        insurance_terms = [
            "等待期", "免赔额", "如实告知", "意外伤害", "既往症",
            "续保", "解除合同", "赔付", "不予赔付", "除外",
            "保障范围", "免责条款", "投保", "理赔", "核保",
            "加费", "拒保", "标准体", "次标准体", "犹豫期",
            "年金", "身故", "全残", "轻症", "重疾", "中症",
            "门诊", "住院", "手术", "药物", "检查费",
        ]
        found = [term for term in insurance_terms if term in description]
        return found or [description[:6]]

    def _generate_summary(
        self,
        intent: str,
        decisions: List[RuleDecision],
        matched_count: int,
    ) -> str:
        if matched_count == 0:
            return f"对意图[{intent}]评估了相关规则，未发现明确匹配项。"
        matched = [d for d in decisions if d.matched]
        rejects = [d for d in matched if d.decision in ("reject", "exclusion")]
        approves = [d for d in matched if d.decision in ("approve", "eligible", "standard_accept")]
        parts = []
        if rejects:
            parts.append(f"发现 {len(rejects)} 条拒绝/除外规则")
        if approves:
            parts.append(f"发现 {len(approves)} 条批准/符合规则")
        if parts:
            return "；".join(parts) + f"。共评估 {len(decisions)} 条规则。"
        return f"对意图[{intent}]评估 {len(decisions)} 条规则，{matched_count} 条匹配。"


def _deep_get(data: Dict[str, Any], dotted_key: str) -> Any:
    if not data or not isinstance(data, dict):
        return None
    val: Any = data
    for k in dotted_key.split("."):
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return None
    return val


def _resolve_variable(value: Any, tool_results: Dict[str, Any]) -> Any:
    if not isinstance(value, str):
        return value
    var_map = {
        "product_min_age": ("eligibility_check", "conditions.min_age"),
        "product_max_age": ("eligibility_check", "conditions.max_age"),
    }
    if value not in var_map:
        return value
    tool_name, dotted = var_map[value]
    tool_data = tool_results.get(tool_name, {})
    resolved = _deep_get(tool_data, dotted)
    if resolved is not None:
        return resolved
    product_id = tool_data.get("product_id")
    if product_id:
        try:
            from runtime.tools.data import PRODUCT_CATALOG
            product = next((p for p in PRODUCT_CATALOG if p["product_id"] == product_id), None)
            if product:
                elig = product.get("eligibility", {})
                if value == "product_min_age":
                    return elig.get("min_age", 0)
                if value == "product_max_age":
                    return elig.get("max_age", 65)
        except Exception:
            pass
    return value


def _compare(
    actual: Any,
    expected: Any,
    operator: str,
    tool_results: Optional[Dict[str, Any]] = None,
) -> bool:
    tool_results = tool_results or {}
    try:
        if isinstance(expected, str) and expected.startswith("product_"):
            expected = _resolve_variable(expected, tool_results)
        if operator == "equals":
            return str(actual).lower() == str(expected).lower()
        if operator == "contains":
            return str(expected).lower() in str(actual).lower()
        if operator == "in":
            if isinstance(expected, list):
                return actual in expected or str(actual) in [str(x) for x in expected]
            return str(actual).lower() in str(expected).lower()
        for op, fn in (
            ("gte", lambda a, e: a >= e),
            ("lte", lambda a, e: a <= e),
            ("gt", lambda a, e: a > e),
            ("lt", lambda a, e: a < e),
        ):
            if operator == op:
                try:
                    return fn(float(actual), float(expected))
                except (TypeError, ValueError):
                    return False
        return str(expected).lower() in str(actual).lower()
    except Exception:
        return False


def _check_condition(
    condition: Dict[str, Any],
    tool_results: Dict[str, Any],
    evidence: List[Dict[str, Any]],
) -> bool:
    field_name = condition.get("field", "")
    operator = condition.get("operator", "equals")
    value = condition.get("value", "")

    for tool_data in tool_results.values():
        actual = _deep_get(tool_data, field_name)
        if actual is not None and _compare(actual, value, operator, tool_results):
            return True

    for ev in evidence[:5]:
        if not isinstance(ev, dict):
            continue
        actual = _deep_get(ev, field_name)
        if actual is None:
            meta = ev.get("metadata", {})
            if isinstance(meta, dict):
                actual = _deep_get(meta, field_name)
        if actual is not None and _compare(actual, value, operator, tool_results):
            return True
    return False
