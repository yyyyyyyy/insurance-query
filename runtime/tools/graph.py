"""Graph Tools for Sprint 2 — EntityLookup and RelationTraversal."""

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from runtime.evidence.contract import make_evidence, SourceType
from runtime.tools.base import BaseTool, ToolResult, ToolStatus
from runtime.tools.ontology_data import ONTOLOGY_ENTITIES, ONTOLOGY_RELATIONS


class EntityLookupInput(BaseModel):
    entity_name: str = Field(default="")
    entity_type: Optional[str] = Field(default=None)


class EntityLookupOutput(BaseModel):
    entities: List[Dict[str, Any]] = Field(default_factory=list)


class EntityLookupTool(BaseTool[EntityLookupInput, EntityLookupOutput]):
    @property
    def name(self) -> str: return "entity_lookup"
    @property
    def description(self) -> str: return "Query ontology entities by name or type"
    @property
    def input_schema(self): return EntityLookupInput
    @property
    def output_schema(self): return EntityLookupOutput

    def execute(self, input_data: EntityLookupInput) -> ToolResult:
        results = []
        name = input_data.entity_name.lower().strip()
        types_to_search = [input_data.entity_type] if input_data.entity_type else list(ONTOLOGY_ENTITIES.keys())

        for etype in types_to_search:
            for entity in ONTOLOGY_ENTITIES.get(etype, []):
                if name:
                    if name not in entity["name"].lower() and not any(
                        name in alias.lower() for alias in entity.get("aliases", [])
                    ):
                        continue
                results.append({
                    "entity_id": entity["entity_id"], "name": entity["name"],
                    "type": entity["type"], "aliases": entity.get("aliases", []),
                    **{k: v for k, v in entity.items() if k not in ("entity_id", "name", "type", "aliases")}
                })

        evidence = [make_evidence(r["entity_id"], r["entity_id"],
                    f"Entity: {r['name']} [{r['type']}]",
                    SourceType.ENTITY_REGISTRY) for r in results]

        status = ToolStatus.SUCCESS if results else ToolStatus.EMPTY
        return ToolResult(tool_name=self.name, status=status,
                         data={"entities": results}, evidence=evidence)


class RelationTraversalInput(BaseModel):
    entity_id: str = Field(default="")
    relation_type: Optional[str] = Field(default=None)
    direction: str = Field(default="outgoing")


class RelationTraversalOutput(BaseModel):
    paths: List[Dict[str, Any]] = Field(default_factory=list)


class RelationTraversalTool(BaseTool[RelationTraversalInput, RelationTraversalOutput]):
    @property
    def name(self) -> str: return "relation_traversal"
    @property
    def description(self) -> str: return "Traverse ontology relations"
    @property
    def input_schema(self): return RelationTraversalInput
    @property
    def output_schema(self): return RelationTraversalOutput

    def execute(self, input_data: RelationTraversalInput) -> ToolResult:
        paths = []
        for rel in ONTOLOGY_RELATIONS:
            if input_data.direction == "outgoing":
                if rel["source"] != input_data.entity_id:
                    continue
            else:
                if rel["target"] != input_data.entity_id:
                    continue
            if input_data.relation_type and rel["relation"] != input_data.relation_type:
                continue
            target_id = rel["target"] if input_data.direction == "outgoing" else rel["source"]
            target_entity = self._resolve_entity(target_id)
            paths.append({
                "source": rel["source"],
                "relation": rel["relation"],
                "target": target_id,
                "target_name": target_entity["name"] if target_entity else "Unknown",
                "target_type": target_entity["type"] if target_entity else "Unknown",
                "evidence": rel.get("evidence", ""),
            })

        evidence = [make_evidence(p["source"], p["target"],
                    f"{p['relation']} -> {p['target_name']}",
                    SourceType.ONTOLOGY) for p in paths]

        status = ToolStatus.SUCCESS if paths else ToolStatus.EMPTY
        return ToolResult(tool_name=self.name, status=status,
                         data={"paths": paths}, evidence=evidence)

    @staticmethod
    def _resolve_entity(entity_id: str) -> Optional[Dict[str, Any]]:
        for entities in ONTOLOGY_ENTITIES.values():
            for e in entities:
                if e["entity_id"] == entity_id:
                    return e
        return None
