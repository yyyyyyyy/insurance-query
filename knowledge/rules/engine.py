"""
Rule Engine — Evaluates 45 decision rules against query context and tool outputs.

Loads rules from knowledge_pack/rules/*.json at initialization. Matches rules
against intent type, tool results, and ontology context. Produces structured
decisions (approve/reject/exclusion/etc.) with confidence and source citations.

Usage:
    engine = RuleEngine()
    decisions = engine.evaluate(intent="coverage_question", tool_results=...)
    for d in decisions:
        print(d.rule_id, d.decision, d.confidence)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ============================================================
# Data Models
# ============================================================


@dataclass
class RuleDecision:
    """A single rule evaluation result."""
    rule_id: str
    domain: str
    description: str
    decision: str  # approve | reject | exclusion | extra_premium | standard_accept | etc.
    action: str
    confidence: str  # HIGH | MEDIUM | LOW
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
    """Result of evaluating all relevant rules against a query."""
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


# ============================================================
# Rule Engine
# ============================================================


class RuleEngine:
    """Evaluates insurance decision rules against query context.

    Supports:
      - Intent-based rule filtering
      - Keyword matching against query text
      - Tool result evaluation (coverage limits, premiums, exclusions)
      - Entity/regulation citation matching
    """

    # Intent → domain mapping
    INTENT_DOMAIN_MAP = {
        "product_comparison": ["claim", "clause"],
        "coverage_question": ["claim", "clause"],
        "claim_process": ["claim"],
        "eligibility_check": ["underwriting", "eligibility"],
        "regulation_lookup": [],  # all regulatory_document source rules
        "price_inquiry": ["claim", "clause"],
        "general_inquiry": [],
    }

    # Decision severity ordering
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
        """Load all rules from knowledge_pack."""
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
        """Evaluate relevant rules against a query.

        Args:
            query_text: Original user query
            intent: Classified intent type
            tool_results: Dictionary of tool_name → output data
            evidence: List of evidence items
            max_rules: Maximum rules to include in result
        """
        tool_results = tool_results or {}
        evidence = evidence or []

        # Step 1: Filter rules by domain
        candidate_rules = self._filter_by_intent(intent)

        # Step 2: Match rules against query context
        matched_decisions: List[RuleDecision] = []
        for rule in candidate_rules:
            decision = self._evaluate_rule(rule, query_text, tool_results, evidence)
            matched_decisions.append(decision)

        # Step 3: Sort by relevance (matched first, then by severity)
        matched_decisions.sort(
            key=lambda d: (
                not d.matched,  # matched rules first
                -self.DECISION_SEVERITY.get(d.decision, 0),  # severe decisions first
                {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(d.confidence, 0),  # high confidence first
            )
        )

        # Limit to max_rules
        matched_decisions = matched_decisions[:max_rules]
        matched_count = sum(1 for d in matched_decisions if d.matched)

        # Step 4: Generate summary
        summary = self._generate_summary(intent, matched_decisions, matched_count)

        return RuleEvaluation(
            intent=intent,
            rules_evaluated=len(candidate_rules),
            rules_matched=matched_count,
            decisions=matched_decisions,
            summary=summary,
        )

    def _filter_by_intent(self, intent: str) -> List[Dict[str, Any]]:
        """Filter rules based on intent type."""
        domains = self.INTENT_DOMAIN_MAP.get(intent, [])

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
        """Evaluate a single rule against query context."""
        conditions = rule.get("if", {}).get("conditions", [])
        then_block = rule.get("then", {})
        description = rule.get("description", "")

        match_reasons = []

        # Check 1: Strict condition matching when conditions exist
        tool_match = False
        if conditions:
            for cond in conditions:
                field = cond.get("field", "")
                if self._check_condition(cond, tool_results, evidence):
                    match_reasons.append(f"condition_matched: {field}")
                    tool_match = True
            # Rules with conditions require at least one condition match
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

        # Check 2: Keyword matching in query text (fallback when no conditions)
        keywords = self._extract_keywords(description)
        query_match = any(kw in query_text for kw in keywords if len(kw) >= 2)

        # Check 3: Evidence content matching (fallback when no conditions)
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
        """Extract key Chinese insurance terms from rule description."""
        insurance_terms = [
            "等待期", "免赔额", "如实告知", "意外伤害", "既往症",
            "续保", "解除合同", "赔付", "不予赔付", "除外",
            "保障范围", "免责条款", "投保", "理赔", "核保",
            "加费", "拒保", "标准体", "次标准体", "犹豫期",
            "年金", "身故", "全残", "轻症", "重疾", "中症",
            "门诊", "住院", "手术", "药物", "检查费",
        ]
        found = []
        for term in insurance_terms:
            if term in description:
                found.append(term)
        return found or [description[:6]]  # fallback: first 6 chars

    @staticmethod
    def _check_condition(
        condition: Dict[str, Any],
        tool_results: Dict[str, Any],
        evidence: List[Dict[str, Any]],
    ) -> bool:
        """Check if a condition is satisfied by tool results or evidence."""
        field = condition.get("field", "")
        operator = condition.get("operator", "equals")
        value = condition.get("value", "")

        # Search in tool results
        for tool_name, tool_data in tool_results.items():
            if _deep_get(tool_data, field) is not None:
                actual = _deep_get(tool_data, field)
                if _compare(actual, value, operator):
                    return True

        # Search in evidence
        for ev in evidence[:5]:
            if str(field) in str(ev):
                return True

        return False

    def _generate_summary(
        self,
        intent: str,
        decisions: List[RuleDecision],
        matched_count: int,
    ) -> str:
        """Generate a human-readable summary of rule evaluation."""
        if matched_count == 0:
            return f"对意图[{intent}]评估了相关规则，未发现明确匹配项。"

        matched = [d for d in decisions if d.matched]

        # Count decisions by type
        rejects = [d for d in matched if d.decision in ("reject", "exclusion")]
        approves = [d for d in matched if d.decision in ("approve", "eligible", "standard_accept")]
        warnings = [d for d in matched if d.confidence == "HIGH" and d.decision in ("reject", "exclusion")]

        parts = []
        if rejects:
            parts.append(f"发现 {len(rejects)} 条拒绝/除外规则")
        if approves:
            parts.append(f"发现 {len(approves)} 条批准/符合规则")
        if warnings:
            high_conf_rejects = [d for d in rejects if d.confidence == "HIGH"]
            if high_conf_rejects:
                parts.append(f"其中 {len(high_conf_rejects)} 条为高置信度拒绝")

        if parts:
            return "；".join(parts) + f"。共评估 {len(decisions)} 条规则。"
        return f"对意图[{intent}]评估 {len(decisions)} 条规则，{matched_count} 条匹配。"


# ============================================================
# Helpers
# ============================================================


def _deep_get(data: Dict[str, Any], dotted_key: str) -> Any:
    """Get a nested dict value using dot notation."""
    if not data or not isinstance(data, dict):
        return None
    keys = dotted_key.split(".")
    val = data
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return None
    return val


def _compare(actual: Any, expected: Any, operator: str) -> bool:
    """Compare actual value against expected using operator."""
    try:
        if operator == "equals":
            return str(actual).lower() == str(expected).lower()
        if operator in ("contains", "in"):
            return str(expected).lower() in str(actual).lower()
        if operator == "gte" and isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            return actual >= expected
        if operator == "lte" and isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            return actual <= expected
        return str(expected).lower() in str(actual).lower()
    except Exception:
        return False
