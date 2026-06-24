"""Pipeline stage: answer composition."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from runtime.llm.plugin import compose_answer_auto
from runtime.llm.answer import _format_citations, _compute_confidence


def build_answer_payload(
    query_text: str,
    intent_type: str,
    intent: Dict[str, Any],
    tool_data: Dict[str, Any],
    accepted_evidence: List[Dict[str, Any]],
    *,
    process_result: Optional[Dict[str, Any]] = None,
    rule_evaluation: Optional[Dict[str, Any]] = None,
    memory_context: Optional[Dict[str, Any]] = None,
    tools_attempted: Optional[List[str]] = None,
    matched_rules: Optional[List[Dict[str, Any]]] = None,
    rule_eval_dict: Optional[Dict[str, Any]] = None,
    accepted_ids: Optional[List[str]] = None,
    canonical_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    answer_text = compose_answer_auto(
        query_text, intent_type, tool_data, accepted_evidence,
        process_result=process_result,
        rule_evaluation=rule_evaluation,
        memory_context=memory_context,
    )
    return {
        "text": answer_text,
        "citations": _format_citations(accepted_evidence),
        "confidence": _compute_confidence(intent, accepted_evidence),
        "intent": intent_type,
        "evidence_count": len(accepted_evidence),
        "tools_used": tools_attempted or [],
        "rule_evaluation": rule_eval_dict or {},
        "matched_rules": matched_rules or [],
        "rule_count": (rule_eval_dict or {}).get("rules_matched", 0),
        "accepted_evidence_ids": accepted_ids or [],
        "canonical_evidence": canonical_payload or {},
    }
