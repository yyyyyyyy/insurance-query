"""Pipeline stage: canonical evidence selection."""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

from runtime.evidence.canonical import CanonicalEvidenceSet
from runtime.evidence.selector import select_evidence_for_answer


def select_canonical_evidence(
    ces: CanonicalEvidenceSet,
    *,
    evidence_threshold: float,
    intent: str,
    force_accept_sources: Set[str] | None = None,
) -> Tuple[List[str], List[str], List[Dict[str, Any]]]:
    accepted_ids, rejected_ids = select_evidence_for_answer(
        ces,
        evidence_threshold=evidence_threshold,
        intent=intent,
        force_accept_sources=force_accept_sources or set(),
    )
    accepted_evidence = ces.to_evidence_dicts(accepted_only=True)
    ces.mark_used_in_answer(accepted_ids)
    return accepted_ids, rejected_ids, accepted_evidence
