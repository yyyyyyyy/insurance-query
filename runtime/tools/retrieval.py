"""Retrieval Tools for Sprint 2."""

import re

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

def _tokenize_chinese(text: str):
    """Split Chinese text into meaningful tokens (bigrams + single chars)."""
    if not text:
        return []
    # Remove common question words and punctuation
    cleaned = re.sub(r'[？?！!，,。.、\s]+', '', text)
    tokens = []
    # 2-char bigrams
    for i in range(len(cleaned) - 1):
        tokens.append(cleaned[i:i+2])
    # 3-char trigrams
    for i in range(len(cleaned) - 2):
        tokens.append(cleaned[i:i+3])
    # Also include the full cleaned text
    tokens.append(cleaned)
    return list(set(tokens))

from runtime.evidence.contract import make_evidence, SourceType
from runtime.tools.base import BaseTool, ToolResult, ToolStatus
from runtime.tools.data import PRODUCT_CATALOG
from runtime.tools.document_data import DOCUMENT_STORE


class ProductSearchInput(BaseModel):
    query: str = Field(default="")
    product_type: Optional[str] = Field(default=None)
    company: Optional[str] = Field(default=None)
    top_k: int = Field(default=5, ge=1, le=20)


class ProductSearchOutput(BaseModel):
    products: List[Dict[str, Any]] = Field(default_factory=list)
    total_found: int = Field(default=0)


class ProductSearchTool(BaseTool[ProductSearchInput, ProductSearchOutput]):
    @property
    def name(self) -> str: return "product_search"
    @property
    def description(self) -> str: return "Search insurance products"
    @property
    def input_schema(self): return ProductSearchInput
    @property
    def output_schema(self): return ProductSearchOutput

    def execute(self, input_data: ProductSearchInput) -> ToolResult:
        query = input_data.query.lower().strip()
        tokens = [t for t in re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', query) if len(t) >= 1]
        results = []
        for p in PRODUCT_CATALOG:
            if input_data.product_type and p["product_type"] != input_data.product_type:
                continue
            if input_data.company and input_data.company not in p["company"]:
                continue
            if tokens:
                searchable = f"{p['name']} {p['product_type']} {p['company_short']}".lower()
                if not any(t in searchable for t in tokens):
                    continue
            results.append({"product_id": p["product_id"], "name": p["name"],
                           "product_type": p["product_type"], "company": p["company_short"]})
            if len(results) >= input_data.top_k:
                break
        evidence = [make_evidence(r["product_id"], r["product_id"],
                    f"{r['name']} ({r['product_type']})",
                    SourceType.PRODUCT_CATALOG, document_title=r["name"])
                    for r in results]
        status = ToolStatus.SUCCESS if results else ToolStatus.EMPTY
        return ToolResult(tool_name=self.name, status=status,
                         data={"products": results, "total_found": len(results)},
                         evidence=evidence)


class DocumentSearchInput(BaseModel):
    query: str = Field(default="")
    document_type: Optional[str] = Field(default=None)
    top_k: int = Field(default=5, ge=1, le=20)


class DocumentSearchOutput(BaseModel):
    chunks: List[Dict[str, Any]] = Field(default_factory=list)
    total_documents: int = Field(default=0)


class DocumentSearchTool(BaseTool[DocumentSearchInput, DocumentSearchOutput]):
    def __init__(self, retriever=None):
        self._retriever = retriever

    def set_retriever(self, retriever) -> None:
        self._retriever = retriever

    @property
    def name(self) -> str: return "document_search"
    @property
    def description(self) -> str: return "Search policy clauses and regulations"
    @property
    def input_schema(self): return DocumentSearchInput
    @property
    def output_schema(self): return DocumentSearchOutput

    def execute(self, input_data: DocumentSearchInput) -> ToolResult:
        query = input_data.query.strip()
        if self._retriever and query:
            doc_type = input_data.document_type or None
            doc_types = [doc_type] if doc_type else None
            hits = self._retriever.retrieve_evidence(
                query, top_k=input_data.top_k, document_types=doc_types,
            )
            chunks = []
            matched_docs = set()
            for h in hits:
                chunks.append({
                    "document_id": h.get("document_id", ""),
                    "document_title": h.get("document_title", ""),
                    "chunk_id": h.get("chunk_id", ""),
                    "clause": h.get("clause", ""),
                    "content": h.get("content", ""),
                    "page": h.get("page"),
                    "score": h.get("score", 0),
                })
                matched_docs.add(h.get("document_id", ""))
            evidence = [
                make_evidence(c["document_id"], c["chunk_id"], c["content"][:200],
                              SourceType.POLICY_CLAUSE, clause=c.get("clause", ""),
                              document_title=c.get("document_title", ""), page=c.get("page"))
                for c in chunks
            ]
            status = ToolStatus.SUCCESS if chunks else ToolStatus.EMPTY
            return ToolResult(tool_name=self.name, status=status,
                              data={"chunks": chunks, "total_documents": len(matched_docs)},
                              evidence=evidence)

        query = query.lower()
        tokens = _tokenize_chinese(query)
        chunks = []
        matched_docs = set()
        for doc in DOCUMENT_STORE:
            if input_data.document_type and doc.get("document_type") != input_data.document_type:
                continue
            for chunk in doc.get("chunks", []):
                chunk_lower = chunk.get("content", "").lower()
                if tokens and not any(t in chunk_lower for t in tokens):
                    continue
                chunks.append({
                    "document_id": doc["document_id"], "document_title": doc["title"],
                    "chunk_id": chunk["chunk_id"], "clause": chunk.get("clause", ""),
                    "content": chunk["content"], "page": chunk.get("page"),
                })
                matched_docs.add(doc["document_id"])
                if len(chunks) >= input_data.top_k:
                    break
            if len(chunks) >= input_data.top_k:
                break
        evidence = [make_evidence(c["document_id"], c["chunk_id"], c["content"][:200],
                    SourceType.POLICY_CLAUSE, clause=c.get("clause", ""),
                    document_title=c["document_title"], page=c.get("page"))
                    for c in chunks]
        status = ToolStatus.SUCCESS if chunks else ToolStatus.EMPTY
        return ToolResult(tool_name=self.name, status=status,
                         data={"chunks": chunks, "total_documents": len(matched_docs)},
                         evidence=evidence)


class RegulationSearchInput(BaseModel):
    query: str = Field(default="")
    top_k: int = Field(default=5, ge=1, le=20)


class RegulationSearchOutput(BaseModel):
    regulations: List[Dict[str, Any]] = Field(default_factory=list)


class RegulationSearchTool(BaseTool[RegulationSearchInput, RegulationSearchOutput]):
    def __init__(self, retriever=None):
        self._retriever = retriever

    def set_retriever(self, retriever) -> None:
        self._retriever = retriever

    @property
    def name(self) -> str: return "regulation_search"
    @property
    def description(self) -> str: return "Search insurance regulations"
    @property
    def input_schema(self): return RegulationSearchInput
    @property
    def output_schema(self): return RegulationSearchOutput

    def execute(self, input_data: RegulationSearchInput) -> ToolResult:
        query = input_data.query.strip()
        if self._retriever and query:
            hits = self._retriever.retrieve_evidence(
                query, top_k=input_data.top_k, document_types=["regulation"],
            )
            by_doc: Dict[str, Dict[str, Any]] = {}
            for h in hits:
                doc_id = h.get("document_id", "")
                if doc_id not in by_doc:
                    by_doc[doc_id] = {
                        "document_id": doc_id,
                        "title": h.get("document_title", doc_id),
                        "chunks": [],
                    }
                by_doc[doc_id]["chunks"].append({
                    "chunk_id": h.get("chunk_id", ""),
                    "clause": h.get("clause", ""),
                    "content": h.get("content", ""),
                    "page": h.get("page"),
                })
            results = list(by_doc.values())[:input_data.top_k]
            evidence = []
            for r in results:
                for c in r["chunks"]:
                    evidence.append(make_evidence(
                        r["document_id"], c["chunk_id"], c["content"][:200],
                        SourceType.REGULATION, clause=c.get("clause", ""),
                        document_title=r["title"], page=c.get("page"),
                    ))
            status = ToolStatus.SUCCESS if results else ToolStatus.EMPTY
            return ToolResult(tool_name=self.name, status=status,
                              data={"regulations": results}, evidence=evidence)

        query = query.lower()
        tokens = _tokenize_chinese(query)
        results = []
        for doc in DOCUMENT_STORE:
            if doc.get("document_type") != "regulation":
                continue
            matched_chunks = []
            for chunk in doc.get("chunks", []):
                chunk_lower = chunk.get("content", "").lower()
                if not tokens or any(t in chunk_lower for t in tokens):
                    matched_chunks.append({
                        "chunk_id": chunk["chunk_id"], "clause": chunk.get("clause", ""),
                        "content": chunk["content"], "page": chunk.get("page"),
                    })
            if matched_chunks:
                results.append({"document_id": doc["document_id"], "title": doc["title"],
                               "chunks": matched_chunks})
            if len(results) >= input_data.top_k:
                break
        evidence = []
        for r in results:
            for c in r["chunks"]:
                evidence.append(make_evidence(r["document_id"], c["chunk_id"],
                    c["content"][:200], SourceType.REGULATION,
                    clause=c.get("clause", ""),
                    document_title=r["title"], page=c.get("page")))
        status = ToolStatus.SUCCESS if results else ToolStatus.EMPTY
        return ToolResult(tool_name=self.name, status=status,
                         data={"regulations": results}, evidence=evidence)
