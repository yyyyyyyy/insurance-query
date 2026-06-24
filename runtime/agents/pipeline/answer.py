"""Pipeline stage: answer composition."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from runtime.llm.plugin import compose_answer_auto
from runtime.llm.answer import _format_citations, _compute_confidence
from runtime.engine.event_store import answer_generated_event

if TYPE_CHECKING:
    from runtime.agents.pipeline._helpers import EventSequencer


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
    answer = {
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
    if process_result:
        answer["process_result"] = process_result
    return answer


def run_answer_stage(
    seq: "EventSequencer",
    answer: Dict[str, Any],
    *,
    accepted_ids: List[str],
    canonical_payload: Dict[str, Any],
) -> Dict[str, Any]:
    seq.append(
        answer_generated_event,
        answer=answer["text"],
        citations=answer.get("citations", []),
        confidence=answer.get("confidence"),
        accepted_evidence_ids=accepted_ids,
        used_in_answer_ids=accepted_ids,
        canonical_evidence_snapshot=canonical_payload,
    )
    return answer
