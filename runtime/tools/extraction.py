"""Extraction Tools for Sprint 2 — AttributeExtraction and ClauseParser."""

from pydantic import BaseModel, Field
from typing import Any, Dict, List
from runtime.evidence.contract import make_evidence, SourceType
from runtime.tools.base import BaseTool, ToolResult, ToolStatus
from runtime.tools.data import PRODUCT_CATALOG

from runtime.tools.field_maps import EXTRACTION_PATTERNS

class AttributeExtractionInput(BaseModel):
    attributes: List[str] = Field(default_factory=list)
    product_ids: List[str] = Field(default_factory=list)


class AttributeExtractionOutput(BaseModel):
    results: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class AttributeExtractionTool(BaseTool[AttributeExtractionInput, AttributeExtractionOutput]):
    @property
    def name(self) -> str: return "attribute_extraction"
    @property
    def description(self) -> str: return "Extract structured attributes from products"
    @property
    def input_schema(self): return AttributeExtractionInput
    @property
    def output_schema(self): return AttributeExtractionOutput

    def execute(self, input_data: AttributeExtractionInput) -> ToolResult:
        results = {}
        evidence = []
        for pid in input_data.product_ids:
            product = next((p for p in PRODUCT_CATALOG if p["product_id"] == pid), None)
            if not product:
                continue
            extracted = {}
            for attr in input_data.attributes:
                field_names = EXTRACTION_PATTERNS.get(attr, [attr])
                for field in field_names:
                    if field in product:
                        extracted[field] = product[field]
            results[pid] = extracted
            evidence.append(make_evidence(pid, pid,
                f"Attributes for {product['name']}", SourceType.PRODUCT_CATALOG,
                document_title=product["name"]))
        status = ToolStatus.SUCCESS if results else ToolStatus.EMPTY
        return ToolResult(tool_name=self.name, status=status,
                         data={"results": results}, evidence=evidence)


class ClauseParserInput(BaseModel):
    document_id: str = Field(default="")
    clause_numbers: List[str] = Field(default_factory=list)


class ClauseParserOutput(BaseModel):
    clauses: List[Dict[str, Any]] = Field(default_factory=list)


class ClauseParserTool(BaseTool[ClauseParserInput, ClauseParserOutput]):
    @property
    def name(self) -> str: return "clause_parser"
    @property
    def description(self) -> str: return "Parse policy clause structure"
    @property
    def input_schema(self): return ClauseParserInput
    @property
    def output_schema(self): return ClauseParserOutput

    def execute(self, input_data: ClauseParserInput) -> ToolResult:
        from runtime.tools.document_data import DOCUMENT_STORE
        doc = next((d for d in DOCUMENT_STORE if d["document_id"] == input_data.document_id), None)
        clauses = []
        evidence = []
        if doc:
            target = set(input_data.clause_numbers) if input_data.clause_numbers else None
            for chunk in doc.get("chunks", []):
                if target and chunk.get("clause") not in target:
                    continue
                clauses.append({"chunk_id": chunk["chunk_id"], "clause": chunk.get("clause", ""),
                               "content": chunk["content"], "page": chunk.get("page")})
                evidence.append(make_evidence(doc["document_id"], chunk["chunk_id"],
                    chunk["content"][:200], SourceType.POLICY_CLAUSE,
                    clause=chunk.get("clause", ""), document_title=doc["title"],
                    page=chunk.get("page")))
        status = ToolStatus.SUCCESS if clauses else ToolStatus.EMPTY
        return ToolResult(tool_name=self.name, status=status,
                         data={"clauses": clauses}, evidence=evidence)
