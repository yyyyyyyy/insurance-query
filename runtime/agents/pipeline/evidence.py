"""Pipeline stage: canonical evidence selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Set, Tuple

from runtime.evidence.canonical import CanonicalEvidenceSet
from runtime.evidence.selector import select_evidence_for_answer
from runtime.evidence.adapters import (
    tool_evidence_to_candidates,
    hybrid_chunks_to_candidates,
    rules_to_candidates,
    process_to_candidates,
    memory_to_candidates,
)
from runtime.engine.event_store import evidence_selected_event
from runtime.agents.pipeline._helpers import EventSequencer


@dataclass
class EvidenceStageResult:
    accepted_ids: List[str]
    rejected_ids: List[str]
    accepted_evidence: List[Dict[str, Any]]
    ces: CanonicalEvidenceSet


def build_and_select_evidence(
    *,
    agent_results: Dict[str, Any],
    retrieval_chunks: List[Dict[str, Any]],
    matched_rules: List[Dict[str, Any]],
    process_result: Dict[str, Any] | None,
    memory_context: Dict[str, Any],
    evidence_threshold: float,
    intent_type: str,
    force_accept_sources: Set[str] | None = None,
) -> Tuple[CanonicalEvidenceSet, List[str], List[str], List[Dict[str, Any]]]:
    ces = CanonicalEvidenceSet()
    for tname, ar_dict in agent_results.items():
        if ar_dict.get("status") == "success" and ar_dict.get("result"):
            ev_list = ar_dict["result"].get("evidence", [])
            ces.add_candidates(tool_evidence_to_candidates(tname, ev_list))
    ces.add_candidates(hybrid_chunks_to_candidates(retrieval_chunks))
    ces.add_candidates(rules_to_candidates(matched_rules))
    if process_result:
        ces.add_candidates(process_to_candidates(process_result))
    ces.add_candidates(memory_to_candidates(memory_context))

    accepted_ids, rejected_ids = select_evidence_for_answer(
        ces,
        evidence_threshold=evidence_threshold,
        intent=intent_type,
        force_accept_sources=force_accept_sources or set(),
    )
    accepted_evidence = ces.to_evidence_dicts(accepted_only=True)
    ces.mark_used_in_answer(accepted_ids)
    return ces, accepted_ids, rejected_ids, accepted_evidence


def run_evidence_stage(
    seq: "EventSequencer",
    *,
    agent_results: Dict[str, Any],
    retrieval_chunks: List[Dict[str, Any]],
    matched_rules: List[Dict[str, Any]],
    process_result: Dict[str, Any] | None,
    memory_context: Dict[str, Any],
    evidence_threshold: float,
    intent_type: str,
    force_accept_sources: Set[str] | None = None,
) -> EvidenceStageResult:
    ces, accepted_ids, rejected_ids, accepted_evidence = build_and_select_evidence(
        agent_results=agent_results,
        retrieval_chunks=retrieval_chunks,
        matched_rules=matched_rules,
        process_result=process_result,
        memory_context=memory_context,
        evidence_threshold=evidence_threshold,
        intent_type=intent_type,
        force_accept_sources=force_accept_sources,
    )

    seq.append(
        evidence_selected_event,
        accepted_ids=accepted_ids,
        rejected_ids=rejected_ids,
        threshold=evidence_threshold,
        snapshot=ces.to_event_payload()["items"],
    )

    return EvidenceStageResult(
        accepted_ids=accepted_ids,
        rejected_ids=rejected_ids,
        accepted_evidence=accepted_evidence,
        ces=ces,
    )
