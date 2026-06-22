"""Canonical evidence decision space for closed-loop runtime kernel v3.

Invariants:
  I1 — event_store is the single execution truth; ctx is a projection.
  I2 — Evidence lifecycle: candidate → selection → accepted; answer reads accepted only.
  I3 — Tools always execute; retrieval produces parallel candidates (no bypass).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

EvidenceSource = Literal["tool", "hybrid", "process", "rule", "memory"]
EvidenceStage = Literal["candidate", "accepted", "rejected"]


def make_canonical_id(source: str, key: str) -> str:
    """Stable canonical ID: {source}:{key}."""
    return f"{source}:{key}"


@dataclass
class CanonicalEvidence:
    canonical_id: str
    source: EvidenceSource
    stage: EvidenceStage = "candidate"
    relevance_score: float = 0.0
    used_in_answer: bool = False
    payload: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_id": self.canonical_id,
            "source": self.source,
            "stage": self.stage,
            "relevance_score": self.relevance_score,
            "used_in_answer": self.used_in_answer,
            "payload": self.payload,
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CanonicalEvidence":
        return cls(
            canonical_id=data["canonical_id"],
            source=data["source"],
            stage=data.get("stage", "candidate"),
            relevance_score=float(data.get("relevance_score", 0)),
            used_in_answer=bool(data.get("used_in_answer", False)),
            payload=dict(data.get("payload", {})),
            provenance=dict(data.get("provenance", {})),
        )


class CanonicalEvidenceSet:
    """Unified evidence decision space for one query."""

    def __init__(self) -> None:
        self._items: Dict[str, CanonicalEvidence] = {}

    def add_candidates(
        self,
        candidates: List[CanonicalEvidence],
        *,
        dedupe: bool = True,
    ) -> None:
        for c in candidates:
            existing = self._items.get(c.canonical_id)
            if existing and dedupe:
                if c.relevance_score > existing.relevance_score:
                    self._items[c.canonical_id] = c
            else:
                self._items[c.canonical_id] = c

    def get(self, canonical_id: str) -> Optional[CanonicalEvidence]:
        return self._items.get(canonical_id)

    def all_items(self) -> List[CanonicalEvidence]:
        return list(self._items.values())

    def candidates(self) -> List[CanonicalEvidence]:
        return [i for i in self._items.values() if i.stage == "candidate"]

    def accepted_items(self) -> List[CanonicalEvidence]:
        return [i for i in self._items.values() if i.stage == "accepted"]

    def rejected_items(self) -> List[CanonicalEvidence]:
        return [i for i in self._items.values() if i.stage == "rejected"]

    def mark_used_in_answer(self, canonical_ids: List[str]) -> None:
        for cid in canonical_ids:
            item = self._items.get(cid)
            if item and item.stage == "accepted":
                item.used_in_answer = True

    def to_evidence_dicts(self, *, accepted_only: bool = True) -> List[Dict[str, Any]]:
        items = self.accepted_items() if accepted_only else self.all_items()
        out: List[Dict[str, Any]] = []
        for item in sorted(items, key=lambda x: -x.relevance_score):
            p = copy.deepcopy(item.payload)
            meta = p.setdefault("metadata", {})
            meta["canonical_id"] = item.canonical_id
            meta["source"] = item.source
            meta["stage"] = item.stage
            meta["used_in_answer"] = item.used_in_answer
            out.append(p)
        return out

    def to_event_payload(self) -> Dict[str, Any]:
        return {
            "items": [i.to_dict() for i in self.all_items()],
            "accepted_ids": [i.canonical_id for i in self.accepted_items()],
            "rejected_ids": [i.canonical_id for i in self.rejected_items()],
        }

    def apply_selection(
        self,
        accepted_ids: List[str],
        rejected_ids: List[str],
    ) -> None:
        for cid in rejected_ids:
            if cid in self._items:
                self._items[cid].stage = "rejected"
        for cid in accepted_ids:
            if cid in self._items:
                self._items[cid].stage = "accepted"
