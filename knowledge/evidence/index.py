"""
Evidence Index System — chunk<=>evidence bidirectional mapping with entity links.
Every chunk traceable. No orphan data.
"""

from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from knowledge.ingestion.pipeline import Chunk

@dataclass
class EvidenceRecord:
    evidence_id: str
    document_id: str
    chunk_id: str
    clause: str
    content: str
    content_hash: str
    source_type: str
    document_title: str = ""
    page: Optional[int] = None
    confidence: float = 1.0
    entity_links: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    def to_dict(self):
        return {"evidence_id":self.evidence_id,"document_id":self.document_id,
                "chunk_id":self.chunk_id,"clause":self.clause,"content":self.content,
                "source_type":self.source_type,"document_title":self.document_title,
                "page":self.page,"confidence":self.confidence,
                "entity_links":self.entity_links}

class EvidenceIndex:
    def __init__(self):
        self._records: Dict[str, EvidenceRecord] = {}
        self._chunk_index: Dict[str, str] = {}
        self._doc_index: Dict[str, List[str]] = {}
        self._entity_index: Dict[str, List[str]] = {}

    def index_chunk(self, chunk: Chunk, source_type: str, document_title: str = "") -> EvidenceRecord:
        h = hashlib.md5(chunk.content.encode()).hexdigest()[:12]
        rec = EvidenceRecord(
            evidence_id=f"EV-{chunk.chunk_id}", document_id=chunk.document_id,
            chunk_id=chunk.chunk_id, clause=chunk.clause, content=chunk.content,
            content_hash=h, source_type=source_type,
            document_title=document_title, page=chunk.page)
        self._records[rec.evidence_id] = rec
        self._chunk_index[chunk.chunk_id] = rec.evidence_id
        self._doc_index.setdefault(chunk.document_id, []).append(rec.evidence_id)
        return rec

    def link_entity(self, evidence_id: str, entity_id: str) -> None:
        rec = self._records.get(evidence_id)
        if rec and entity_id not in rec.entity_links:
            rec.entity_links.append(entity_id)
            self._entity_index.setdefault(entity_id, []).append(evidence_id)

    def get_by_chunk(self, chunk_id: str) -> Optional[EvidenceRecord]:
        eid = self._chunk_index.get(chunk_id)
        return self._records.get(eid) if eid else None

    def get_by_document(self, document_id: str) -> List[EvidenceRecord]:
        return [self._records[eid] for eid in self._doc_index.get(document_id,[]) if eid in self._records]

    def get_by_entity(self, entity_id: str) -> List[EvidenceRecord]:
        return [self._records[eid] for eid in self._entity_index.get(entity_id,[]) if eid in self._records]

    def record_count(self) -> int: return len(self._records)

    def verify_traceability(self, document_id: str) -> Dict[str, Any]:
        records = self.get_by_document(document_id)
        linked = sum(1 for r in records if r.entity_links)
        return {"document_id":document_id,"total":len(records),
                "linked":linked,"orphan":len(records)-linked}
