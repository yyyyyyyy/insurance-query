"""
Ontology Auto-Extraction — Extract entities and relations from ingested documents.

Scans document chunks for insurance terms (products, diseases, regulations) and
suggests new ontology entities/relations for manual review or auto-addition.

Usage:
    extractor = OntologyExtractor(ontology_graph)
    suggestions = extractor.extract_from_chunks(chunks)
    for s in suggestions:
        print(s.entity_name, s.entity_type, s.confidence)
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from knowledge.ontology.graph import EntityType


# Keyword patterns for auto-extraction
EXTRACTION_PATTERNS = {
    EntityType.PRODUCT: re.compile(
        r"([\u4e00-\u9fff]{2,6}(?:保|险|医疗|寿险|年金|意外))"
    ),
    EntityType.DISEASE: re.compile(
        r"((?:恶性|急性|慢性|严重|原发|继发)?[\u4e00-\u9fff]{2,4}(?:癌|瘤|病|症|炎|梗死|衰竭|坏死|障碍))"
    ),
    EntityType.REGULATION: re.compile(
        r"(《[\u4e00-\u9fff]+办法》|《[\u4e00-\u9fff]+条例》|《[\u4e00-\u9fff]+法》"
        r"|[\u4e00-\u9fff]+管理办法|[\u4e00-\u9fff]+规范)"
    ),
    EntityType.COVERAGE: re.compile(
        r"([\u4e00-\u9fff]{2,8}(?:保险金|保障|医疗|手术|给付|报销))"
    ),
    EntityType.RULE: re.compile(
        r"([\u4e00-\u9fff]{2,6}(?:期|额|条款|义务|责任))"
    ),
}

# Known terms to filter out false positives
STOP_TERMS: Set[str] = {
    "保险金", "医疗费", "手续费", "保险费", "本合同", "被保险",
    "保险费率", "保险期间", "住院费用", "保险人", "投保人",
    "受益人", "理赔金",
}


@dataclass
class EntitySuggestion:
    """Suggested new ontology entity from document analysis."""
    entity_name: str
    entity_type: EntityType
    confidence: float  # 0.0 - 1.0
    source_document: str
    context: str = ""
    existing: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_name": self.entity_name,
            "entity_type": self.entity_type.value,
            "confidence": round(self.confidence, 2),
            "source_document": self.source_document,
            "existing": self.existing,
        }


@dataclass
class RelationSuggestion:
    """Suggested new relation from co-occurrence analysis."""
    source_entity: str
    target_entity: str
    relation_type: str  # contains | covers | defines | etc.
    confidence: float
    evidence: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source_entity,
            "target": self.target_entity,
            "relation": self.relation_type,
            "confidence": round(self.confidence, 2),
        }


class OntologyExtractor:
    """Auto-extracts entity and relation suggestions from document chunks."""

    def __init__(self, ontology=None):
        self._ontology = ontology
        self._known_entities: Set[str] = set()
        if ontology:
            self._known_entities = {e.name for e in ontology._entities.values()}

    def extract_entities(
        self,
        chunks: List[Any],
        document_id: str = "",
    ) -> List[EntitySuggestion]:
        """Extract entity suggestions from document chunks."""
        all_text = " ".join(
            getattr(c, "content", str(c)) for c in (chunks or [])
        )
        if not all_text:
            return []

        suggestions: List[EntitySuggestion] = []
        entity_counter: Counter = Counter()

        for entity_type, pattern in EXTRACTION_PATTERNS.items():
            matches = pattern.findall(all_text)
            for match in matches:
                match_str = match if isinstance(match, str) else match[0] if isinstance(match, tuple) else str(match)
                match_str = match_str.strip()
                if len(match_str) < 2 or match_str in STOP_TERMS:
                    continue
                entity_counter[(match_str, entity_type)] += 1

        # Filter and score
        total_matches = sum(entity_counter.values()) or 1
        for (name, etype), count in entity_counter.most_common(30):
            if name in self._known_entities:
                suggestions.append(EntitySuggestion(
                    entity_name=name, entity_type=etype,
                    confidence=min(count / max(total_matches * 0.1, 1), 1.0),
                    source_document=document_id, existing=True,
                ))
            elif count >= 2:  # Require at least 2 occurrences
                suggestions.append(EntitySuggestion(
                    entity_name=name, entity_type=etype,
                    confidence=min(count / max(total_matches * 0.1, 1), 1.0),
                    source_document=document_id,
                ))

        return suggestions

    def extract_relations(
        self,
        entity_suggestions: List[EntitySuggestion],
        chunk_texts: List[str],
    ) -> List[RelationSuggestion]:
        """Suggest relations based on entity co-occurrence in chunks."""
        relations = []
        entity_names = {s.entity_name for s in entity_suggestions if s.confidence > 0.3}

        for text in chunk_texts[:50]:  # Sample first 50 chunks
            found = [name for name in entity_names if name in text]
            for i, src in enumerate(found):
                for tgt in found[i + 1:]:
                    # Simple heuristic: entities in same clause are related
                    relations.append(RelationSuggestion(
                        source_entity=src, target_entity=tgt,
                        relation_type="references",
                        confidence=0.5,
                        evidence=text[:100],
                    ))

        # Deduplicate
        seen = set()
        unique = []
        for r in relations:
            key = (r.source_entity, r.target_entity)
            if key not in seen:
                seen.add(key)
                unique.append(r)

        return unique[:20]

    def add_to_ontology(
        self,
        suggestions: List[EntitySuggestion],
        min_confidence: float = 0.5,
    ) -> int:
        """Auto-add high-confidence suggestions to the ontology."""
        if not self._ontology:
            return 0

        from knowledge.ontology.graph import OntologyEntity

        added = 0
        for s in suggestions:
            if s.existing or s.confidence < min_confidence:
                continue
            try:
                entity_id = f"ENT-AUTO-{s.entity_type.value[:4]}-{added:03d}"
                self._ontology.add_entity(OntologyEntity(
                    entity_id=entity_id,
                    name=s.entity_name,
                    entity_type=s.entity_type,
                ))
                self._known_entities.add(s.entity_name)
                added += 1
            except ValueError:
                pass  # Already exists

        return added
