"""Pipeline stage: retrieval execution."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from knowledge.retrieval.engine import HybridRetriever


def run_retrieval(
    retriever: Optional[HybridRetriever],
    query: str,
    *,
    top_k: int = 5,
    ontology_context: Optional[List[str]] = None,
    weights: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    if retriever is None:
        return []
    w = weights or {}
    results = retriever.retrieve_evidence(
        query,
        top_k=top_k,
        ontology_context=ontology_context or [],
        bm25_weight=w.get("bm25_weight", 0.4),
        vector_weight=w.get("vector_weight", 0.4),
        ontology_boost=w.get("ontology_weight", 0.2),
    )
    return results
