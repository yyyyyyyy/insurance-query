"""Adapters: pipeline outputs → CanonicalEvidence candidates."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from runtime.evidence.canonical import CanonicalEvidence, make_canonical_id
from runtime.evidence.contract import SourceType


def _evidence_score(item: Dict[str, Any], default: float = 0.5) -> float:
    if "score" in item and item["score"] is not None:
        return float(item["score"])
    status = item.get("status", "")
    if status == "EXACT":
        return 0.9
    if status == "RELEVANT":
        return 0.7
    return default


def tool_evidence_to_candidates(
    tool_name: str,
    evidence_list: List[Dict[str, Any]],
) -> List[CanonicalEvidence]:
    candidates: List[CanonicalEvidence] = []
    for i, ev in enumerate(evidence_list):
        chunk_id = ev.get("chunk_id") or ev.get("product_id") or f"idx-{i}"
        cid = make_canonical_id("tool", f"{tool_name}:{chunk_id}")
        payload = dict(ev)
        candidates.append(
            CanonicalEvidence(
                canonical_id=cid,
                source="tool",
                stage="candidate",
                relevance_score=_evidence_score(ev, 0.6),
                payload=payload,
                provenance={"tool_name": tool_name, "rank": i},
            )
        )
    return candidates


def hybrid_chunks_to_candidates(chunks: List[Dict[str, Any]]) -> List[CanonicalEvidence]:
    candidates: List[CanonicalEvidence] = []
    for i, ch in enumerate(chunks):
        chunk_id = ch.get("chunk_id", f"hybrid-{i}")
        cid = make_canonical_id("hybrid", chunk_id)
        score = float(ch.get("score", 0.5))
        payload = {
            "document_id": ch.get("document_id", ""),
            "chunk_id": chunk_id,
            "clause": ch.get("clause", ""),
            "content": ch.get("content", ""),
            "source_type": SourceType.POLICY_CLAUSE.value,
            "score": score,
            "metadata": {"source": "hybrid", "stage": "candidate"},
        }
        candidates.append(
            CanonicalEvidence(
                canonical_id=cid,
                source="hybrid",
                stage="candidate",
                relevance_score=score,
                payload=payload,
                provenance={
                    "rank": i,
                    "feature_contribution": ch.get("feature_contribution", {}),
                },
            )
        )
    return candidates


def rules_to_candidates(matched_decisions: List[Dict[str, Any]]) -> List[CanonicalEvidence]:
    candidates: List[CanonicalEvidence] = []
    for d in matched_decisions:
        if not d.get("matched"):
            continue
        rule_id = d.get("rule_id") or d.get("id") or d.get("name", "unknown")
        cid = make_canonical_id("rule", str(rule_id))
        candidates.append(
            CanonicalEvidence(
                canonical_id=cid,
                source="rule",
                stage="candidate",
                relevance_score=0.95,
                payload={
                    "rule_id": rule_id,
                    "decision": d.get("decision", ""),
                    "reason": d.get("reason", d.get("message", "")),
                    "content": d.get("reason", d.get("message", str(rule_id))),
                },
                provenance={"matched": True, **d},
            )
        )
    return candidates


def process_to_candidates(process_result: Optional[Dict[str, Any]]) -> List[CanonicalEvidence]:
    if not process_result:
        return []
    pname = process_result.get("process_name", "process")
    terminal = process_result.get("terminal_state", "")
    outcome = process_result.get("outcome", terminal)
    cid = make_canonical_id("process", f"{pname}:{terminal}")
    return [
        CanonicalEvidence(
            canonical_id=cid,
            source="process",
            stage="candidate",
            relevance_score=0.9,
            payload={
                "process_name": pname,
                "terminal_state": terminal,
                "outcome": outcome,
                "path": process_result.get("path", []),
                "content": outcome,
            },
            provenance=dict(process_result),
        )
    ]


def memory_to_candidates(memory_context: Dict[str, Any]) -> List[CanonicalEvidence]:
    candidates: List[CanonicalEvidence] = []
    for i, prod in enumerate(memory_context.get("previous_products", [])[:3]):
        if not prod:
            continue
        cid = make_canonical_id("memory", f"product:{prod}")
        candidates.append(
            CanonicalEvidence(
                canonical_id=cid,
                source="memory",
                stage="candidate",
                relevance_score=0.3,
                payload={"content": prod, "type": "previous_product"},
                provenance={"index": i},
            )
        )
    return candidates
