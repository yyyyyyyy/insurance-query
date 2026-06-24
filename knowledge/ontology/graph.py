"""
Insurance Ontology System — NetworkX-backed directed graph.
Entity types: Product, Coverage, Disease, Rule, Regulation
Relations: contains, covers, defines, implements, regulated_by
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set
import networkx as nx

class EntityType(str, Enum):
    PRODUCT = "Product"
    COVERAGE = "Coverage"
    DISEASE = "Disease"
    RULE = "Rule"
    REGULATION = "Regulation"
    CLAUSE = "Clause"
    EXCLUSION = "Exclusion"

class RelationType(str, Enum):
    CONTAINS = "contains"
    COVERS = "covers"
    DEFINES = "defines"
    IMPLEMENTS = "implements"
    REGULATED_BY = "regulated_by"
    EXCLUDES = "excludes"
    REFERENCES = "references"

@dataclass
class OntologyEntity:
    entity_id: str
    name: str
    entity_type: EntityType
    aliases: List[str] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)
    evidence_refs: List[str] = field(default_factory=list)
    def to_dict(self) -> Dict[str, Any]:
        return {"entity_id":self.entity_id,"name":self.name,
                "entity_type":self.entity_type.value,"aliases":self.aliases,
                "properties":self.properties,"evidence_refs":self.evidence_refs}

@dataclass
class OntologyRelation:
    source_id: str
    target_id: str
    relation_type: RelationType
    evidence_refs: List[str] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> Dict[str, Any]:
        return {"source_id":self.source_id,"target_id":self.target_id,
                "relation_type":self.relation_type.value,
                "evidence_refs":self.evidence_refs,"properties":self.properties}

class OntologyGraph:
    def __init__(self):
        self._graph = nx.DiGraph()
        self._entities: Dict[str, OntologyEntity] = {}
        self._alias_index: Dict[str, str] = {}
        self._type_index: Dict[EntityType, Set[str]] = {t: set() for t in EntityType}

    def add_entity(self, entity: OntologyEntity) -> OntologyEntity:
        if entity.entity_id in self._entities:
            raise ValueError(f"Entity exists: {entity.entity_id}")
        self._entities[entity.entity_id] = entity
        self._graph.add_node(entity.entity_id, name=entity.name,
                            entity_type=entity.entity_type.value,
                            properties=entity.properties)
        self._type_index[entity.entity_type].add(entity.entity_id)
        for alias in entity.aliases:
            self._alias_index.setdefault(alias.lower(), entity.entity_id)
        self._alias_index[entity.name.lower()] = entity.entity_id
        return entity

    def get_entity(self, entity_id: str) -> Optional[OntologyEntity]:
        return self._entities.get(entity_id)

    def lookup(self, name: str, entity_type: Optional[EntityType] = None) -> List[OntologyEntity]:
        results = []
        eid = self._alias_index.get(name.lower())
        if eid:
            entity = self._entities.get(eid)
            if entity and (entity_type is None or entity.entity_type == entity_type):
                results.append(entity)
        name_lower = name.lower()
        for eid2, entity in self._entities.items():
            if entity_type and entity.entity_type != entity_type:
                continue
            if eid2 == eid:
                continue
            if name_lower in entity.name.lower():
                results.append(entity)
                continue
            for alias in entity.aliases:
                if name_lower in alias.lower():
                    results.append(entity)
                    break
        return results

    def get_entities_by_type(self, entity_type: EntityType) -> List[OntologyEntity]:
        ids = self._type_index.get(entity_type, set())
        return [self._entities[eid] for eid in ids if eid in self._entities]

    def entity_count(self) -> int:
        return len(self._entities)

    def add_relation(self, relation: OntologyRelation) -> OntologyRelation:
        if relation.source_id not in self._entities:
            raise ValueError(f"Source not found: {relation.source_id}")
        if relation.target_id not in self._entities:
            raise ValueError(f"Target not found: {relation.target_id}")
        self._graph.add_edge(relation.source_id, relation.target_id,
                            relation_type=relation.relation_type.value,
                            evidence_refs=relation.evidence_refs,
                            properties=relation.properties)
        return relation

    def get_relations(self, source_id=None, target_id=None,
                      relation_type=None) -> List[OntologyRelation]:
        results = []
        for u, v, data in self._graph.edges(data=True):
            if source_id and u != source_id:
                continue
            if target_id and v != target_id:
                continue
            if relation_type and data.get("relation_type") != relation_type.value:
                continue
            results.append(OntologyRelation(
                source_id=u, target_id=v,
                relation_type=RelationType(data["relation_type"]),
                evidence_refs=data.get("evidence_refs", []),
                properties=data.get("properties", {})))
        return results

    def get_outgoing(self, entity_id: str, relation_type=None) -> List[OntologyRelation]:
        if entity_id not in self._graph:
            return []
        results = []
        for _, v, data in self._graph.out_edges(entity_id, data=True):
            if relation_type and data.get("relation_type") != relation_type.value:
                continue
            results.append(OntologyRelation(
                source_id=entity_id, target_id=v,
                relation_type=RelationType(data["relation_type"]),
                evidence_refs=data.get("evidence_refs", []),
                properties=data.get("properties", {})))
        return results

    def get_incoming(self, entity_id: str, relation_type=None) -> List[OntologyRelation]:
        if entity_id not in self._graph:
            return []
        results = []
        for u, _, data in self._graph.in_edges(entity_id, data=True):
            if relation_type and data.get("relation_type") != relation_type.value:
                continue
            results.append(OntologyRelation(
                source_id=u, target_id=entity_id,
                relation_type=RelationType(data["relation_type"]),
                evidence_refs=data.get("evidence_refs", []),
                properties=data.get("properties", {})))
        return results

    def find_paths(self, source_id: str, target_id: str, max_depth: int = 5) -> List[List[OntologyRelation]]:
        if source_id not in self._graph or target_id not in self._graph:
            return []
        paths = []
        try:
            for path in nx.all_simple_paths(self._graph, source_id, target_id, cutoff=max_depth):
                rels = []
                for i in range(len(path) - 1):
                    d = self._graph.edges[path[i], path[i + 1]]
                    rels.append(OntologyRelation(
                        source_id=path[i], target_id=path[i + 1],
                        relation_type=RelationType(d["relation_type"]),
                        evidence_refs=d.get("evidence_refs", []),
                        properties=d.get("properties", {})))
                paths.append(rels)
        except nx.NetworkXNoPath:
            pass
        return paths

    def expand_context(self, entity_ids: List[str],
                       relation_types: Optional[List[RelationType]] = None,
                       max_depth: int = 2, max_results: int = 20) -> List[OntologyEntity]:
        seed_set = set(entity_ids)
        visited = set(seed_set)
        frontier = set(seed_set)
        for _ in range(max_depth):
            next_frontier = set()
            for node in frontier:
                for neighbor in self._graph.neighbors(node):
                    if neighbor in visited:
                        continue
                    d = self._graph.edges[node, neighbor]
                    if relation_types and RelationType(d["relation_type"]) not in relation_types:
                        continue
                    next_frontier.add(neighbor)
                    visited.add(neighbor)
            if not next_frontier:
                break
            frontier = next_frontier
        result = [self._entities[eid] for eid in (visited - seed_set) if eid in self._entities]
        return result[:max_results]

    def get_neighborhood(self, entity_id: str, radius: int = 1) -> Dict[str, Any]:
        if entity_id not in self._graph:
            return {}
        nodes = set()
        edges = []
        frontier = {entity_id}
        for _ in range(radius):
            nf = set()
            for node in frontier:
                nodes.add(node)
                for _, v in self._graph.out_edges(node):
                    rel_type = self._graph.edges[node, v].get("relation_type", "")
                    edges.append({"source": node, "target": v, "type": rel_type})
                    if v not in nodes:
                        nf.add(v)
                for u, _ in self._graph.in_edges(node):
                    rel_type = self._graph.edges[u, node].get("relation_type", "")
                    edges.append({"source": u, "target": node, "type": rel_type})
                    if u not in nodes:
                        nf.add(u)
            frontier = nf
        return {"center":entity_id,
                "entities":[self._entities[n].to_dict() for n in nodes if n in self._entities],
                "relations":edges}

    def statistics(self) -> Dict[str, Any]:
        return {"entity_count":len(self._entities),
                "relation_count":self._graph.number_of_edges(),
                "by_type":{t.value:len(ids) for t,ids in self._type_index.items() if ids}}

    def to_dict(self) -> Dict[str, Any]:
        return {"entities":{eid:e.to_dict() for eid,e in self._entities.items()},
                "relations":[{"source_id":u,"target_id":v,"relation_type":d["relation_type"],
                              "evidence_refs":d.get("evidence_refs",[])}
                             for u,v,d in self._graph.edges(data=True)]}
