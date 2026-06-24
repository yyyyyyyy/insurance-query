"""Graph Tools — EntityLookup and RelationTraversal backed by OntologyGraph."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from pydantic import BaseModel, Field

from runtime.evidence.contract import make_evidence, SourceType
from runtime.tools.base import BaseTool, ToolResult, ToolStatus

if TYPE_CHECKING:
    from knowledge.ontology.graph import EntityType, OntologyGraph


class EntityLookupInput(BaseModel):
    entity_name: str = Field(default="")
    entity_type: Optional[str] = Field(default=None)


class EntityLookupOutput(BaseModel):
    entities: List[Dict[str, Any]] = Field(default_factory=list)


class EntityLookupTool(BaseTool[EntityLookupInput, EntityLookupOutput]):
    def __init__(self, ontology: Optional["OntologyGraph"] = None):
        self._ontology = ontology

    def set_ontology(self, ontology: "OntologyGraph") -> None:
        self._ontology = ontology

    def _graph(self) -> "OntologyGraph":
        if self._ontology is None:
            from knowledge.ontology.builder import build_insurance_ontology
            self._ontology = build_insurance_ontology()
        return self._ontology

    @property
    def name(self) -> str:
        return "entity_lookup"

    @property
    def description(self) -> str:
        return "Query ontology entities by name or type"

    @property
    def input_schema(self):
        return EntityLookupInput

    @property
    def output_schema(self):
        return EntityLookupOutput

    def execute(self, input_data: EntityLookupInput) -> ToolResult:
        from knowledge.ontology.graph import EntityType

        g = self._graph()
        results: List[Dict[str, Any]] = []
        name = input_data.entity_name.strip()

        etype: Optional[EntityType] = None
        if input_data.entity_type:
            try:
                etype = EntityType(input_data.entity_type)
            except ValueError:
                pass

        if name:
            for entity in g.lookup(name, etype):
                results.append(self._entity_dict(entity))
        elif etype:
            for entity in g.get_entities_by_type(etype):
                results.append(self._entity_dict(entity))
        else:
            for entity in g._entities.values():
                results.append(self._entity_dict(entity))

        seen = set()
        unique = []
        for r in results:
            if r["entity_id"] not in seen:
                seen.add(r["entity_id"])
                unique.append(r)

        evidence = [
            make_evidence(r["entity_id"], r["entity_id"],
                          f"Entity: {r['name']} [{r['type']}]",
                          SourceType.ENTITY_REGISTRY)
            for r in unique
        ]
        status = ToolStatus.SUCCESS if unique else ToolStatus.EMPTY
        return ToolResult(tool_name=self.name, status=status,
                          data={"entities": unique}, evidence=evidence)

    @staticmethod
    def _entity_dict(entity) -> Dict[str, Any]:
        return {
            "entity_id": entity.entity_id,
            "name": entity.name,
            "type": entity.entity_type.value,
            "aliases": entity.aliases,
            **entity.properties,
        }


class RelationTraversalInput(BaseModel):
    entity_id: str = Field(default="")
    relation_type: Optional[str] = Field(default=None)
    direction: str = Field(default="outgoing")


class RelationTraversalOutput(BaseModel):
    paths: List[Dict[str, Any]] = Field(default_factory=list)


class RelationTraversalTool(BaseTool[RelationTraversalInput, RelationTraversalOutput]):
    def __init__(self, ontology: Optional["OntologyGraph"] = None):
        self._ontology = ontology

    def set_ontology(self, ontology: "OntologyGraph") -> None:
        self._ontology = ontology

    def _graph(self) -> "OntologyGraph":
        if self._ontology is None:
            from knowledge.ontology.builder import build_insurance_ontology
            self._ontology = build_insurance_ontology()
        return self._ontology

    @property
    def name(self) -> str:
        return "relation_traversal"

    @property
    def description(self) -> str:
        return "Traverse ontology relations"

    @property
    def input_schema(self):
        return RelationTraversalInput

    @property
    def output_schema(self):
        return RelationTraversalOutput

    def execute(self, input_data: RelationTraversalInput) -> ToolResult:
        from knowledge.ontology.graph import RelationType

        g = self._graph()
        rel_type = None
        if input_data.relation_type:
            try:
                rel_type = RelationType(input_data.relation_type)
            except ValueError:
                pass

        if input_data.direction == "outgoing":
            rels = g.get_outgoing(input_data.entity_id, rel_type)
        else:
            rels = g.get_incoming(input_data.entity_id, rel_type)

        paths = []
        for rel in rels:
            target_id = rel.target_id if input_data.direction == "outgoing" else rel.source_id
            target = g.get_entity(target_id)
            paths.append({
                "source": rel.source_id,
                "relation": rel.relation_type.value,
                "target": target_id,
                "target_name": target.name if target else "Unknown",
                "target_type": target.entity_type.value if target else "Unknown",
                "evidence": ",".join(rel.evidence_refs) if rel.evidence_refs else "",
            })

        evidence = [
            make_evidence(p["source"], p["target"],
                          f"{p['relation']} -> {p['target_name']}",
                          SourceType.ONTOLOGY)
            for p in paths
        ]
        status = ToolStatus.SUCCESS if paths else ToolStatus.EMPTY
        return ToolResult(tool_name=self.name, status=status,
                          data={"paths": paths}, evidence=evidence)
