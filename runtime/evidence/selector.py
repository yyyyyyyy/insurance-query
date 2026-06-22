"""Evidence selection gate: candidate → accepted | rejected."""

from __future__ import annotations

from typing import List, Optional, Set

from runtime.evidence.canonical import CanonicalEvidenceSet

CLAIM_INTENTS = frozenset({"claim_process", "coverage_question"})
UW_INTENTS = frozenset({"eligibility_check"})


def select_evidence_for_answer(
    ces: CanonicalEvidenceSet,
    *,
    evidence_threshold: float = 0.0,
    max_accepted: int = 15,
    intent: str = "general_inquiry",
    force_accept_sources: Optional[Set[str]] = None,
) -> tuple[List[str], List[str]]:
    """Select accepted/rejected canonical IDs.

    Returns (accepted_ids, rejected_ids).
    """
    force = force_accept_sources or set()
    force_rule = "rule" in force
    force_process = "process" in force

    ranked = sorted(
        ces.candidates(),
        key=lambda x: (-x.relevance_score, x.canonical_id),
    )

    accepted_ids: List[str] = []
    rejected_ids: List[str] = []
    seen: Set[str] = set()

    for item in ranked:
        if item.canonical_id in seen:
            continue
        seen.add(item.canonical_id)

        force_accept = (
            (force_rule and item.source == "rule")
            or (force_process and item.source == "process")
            or (item.source == "process" and intent in CLAIM_INTENTS | UW_INTENTS)
            or (item.source == "rule" and item.provenance.get("matched"))
        )

        if force_accept:
            accepted_ids.append(item.canonical_id)
        elif item.relevance_score < evidence_threshold:
            rejected_ids.append(item.canonical_id)
        elif len(accepted_ids) < max_accepted:
            accepted_ids.append(item.canonical_id)
        else:
            rejected_ids.append(item.canonical_id)

    ces.apply_selection(accepted_ids, rejected_ids)
    return accepted_ids, rejected_ids
