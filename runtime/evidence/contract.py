"""
Evidence Contract Model — InsureQuery Runtime Sprint 2.

ARCHITECTURE RULE #2: All answers MUST have evidence.
ARCHITECTURE RULE #4: Tools return evidence, not prose.

Evidence follows the contract defined in 06-Tool-Contracts.md:
  - document_id: source document
  - chunk_id: specific chunk within document
  - clause: applicable clause number
  - content: verbatim excerpt from source
  - source_type: classification of evidence type
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EvidenceStatus(str, Enum):
    """Evidence quality classification."""
    EXACT = "EXACT"          # Direct clause match
    RELEVANT = "RELEVANT"    # Semantically relevant
    CONTEXT = "CONTEXT"      # Surrounding context
    INFERRED = "INFERRED"    # Derived from multiple sources


class SourceType(str, Enum):
    """Classification of evidence source."""
    POLICY_CLAUSE = "policy_clause"
    REGULATION = "regulation"
    PRODUCT_CATALOG = "product_catalog"
    ONTOLOGY = "ontology"
    COMPARISON_ENGINE = "comparison_engine"
    ENTITY_REGISTRY = "entity_registry"


@dataclass
class EvidenceItem:
    """Single piece of traceable evidence.

    Every fact returned by a tool must be backed by at least one EvidenceItem.
    """

    document_id: str
    chunk_id: str
    clause: str
    content: str
    source_type: SourceType
    document_title: str = ""
    page: Optional[int] = None
    status: EvidenceStatus = EvidenceStatus.EXACT
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "clause": self.clause,
            "content": self.content,
            "source_type": self.source_type.value,
            "document_title": self.document_title,
            "page": self.page,
            "status": self.status.value,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceItem":
        return cls(
            document_id=data["document_id"],
            chunk_id=data["chunk_id"],
            clause=data.get("clause", ""),
            content=data.get("content", ""),
            source_type=SourceType(data.get("source_type", "product_catalog")),
            document_title=data.get("document_title", ""),
            page=data.get("page"),
            status=EvidenceStatus(data.get("status", "EXACT")),
            metadata=data.get("metadata", {}),
        )


@dataclass
class EvidenceBundle:
    """Collection of evidence items from a single tool execution."""

    items: List[EvidenceItem] = field(default_factory=list)
    tool_name: str = ""
    source: str = ""

    def add(self, item: EvidenceItem) -> None:
        self.items.append(item)

    def to_list(self) -> List[Dict[str, Any]]:
        return [item.to_dict() for item in self.items]

    def __len__(self) -> int:
        return len(self.items)

    def __bool__(self) -> bool:
        return len(self.items) > 0


def make_evidence(
    document_id: str,
    chunk_id: str,
    content: str,
    source_type: SourceType = SourceType.POLICY_CLAUSE,
    clause: str = "",
    document_title: str = "",
    page: Optional[int] = None,
    status: EvidenceStatus = EvidenceStatus.EXACT,
    **metadata,
) -> EvidenceItem:
    """Factory helper for creating evidence items."""
    return EvidenceItem(
        document_id=document_id,
        chunk_id=chunk_id,
        clause=clause,
        content=content,
        source_type=source_type,
        document_title=document_title,
        page=page,
        status=status,
        metadata=metadata,
    )
