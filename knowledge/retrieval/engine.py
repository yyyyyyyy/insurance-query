"""
Hybrid Retrieval Engine — BM25 + Vector + Ontology-Guided.

Query Flow:
  User Query -> Intent -> Ontology Expansion -> Hybrid Retrieval -> Evidence Ranking

Sprint 6: Integrated ChromaDB (vector acceleration) and sentence-transformers
embeddings with automatic fallback to TF-IDF.
"""

from __future__ import annotations
import math
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np
from knowledge.ingestion.pipeline import Chunk, ChunkStore, EmbeddingGenerator
from knowledge.ontology.graph import OntologyGraph, OntologyEntity, EntityType

class BM25Scorer:
    """BM25 keyword relevance scoring."""
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1; self.b = b
        self._doc_lengths: List[int] = []
        self._avg_dl: float = 0.0
        self._doc_count: int = 0
        self._term_df: Dict[str, int] = defaultdict(int)
        self._doc_term_freqs: List[Dict[str, int]] = []
        self._fitted = False

    def fit(self, texts: List[str]):
        self._doc_count = len(texts)
        self._doc_lengths = [len(self._tokenize(t)) for t in texts]
        self._avg_dl = sum(self._doc_lengths) / max(self._doc_count, 1)
        for text in texts:
            tokens = self._tokenize(text)
            tf = defaultdict(int)
            for t in tokens: tf[t] += 1
            self._doc_term_freqs.append(dict(tf))
            for t in set(tokens): self._term_df[t] += 1
        self._fitted = True

    def score(self, query: str, doc_idx: int) -> float:
        if not self._fitted: return 0.0
        q_tokens = self._tokenize(query)
        dl = self._doc_lengths[doc_idx]
        tf = self._doc_term_freqs[doc_idx]
        score = 0.0
        for t in q_tokens:
            df = self._term_df.get(t, 0)
            if df == 0: continue
            idf = math.log((self._doc_count - df + 0.5) / (df + 0.5) + 1.0)
            term_freq = tf.get(t, 0)
            numerator = term_freq * (self.k1 + 1)
            denominator = term_freq + self.k1 * (1 - self.b + self.b * dl / self._avg_dl)
            score += idf * numerator / max(denominator, 0.001)
        return score

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return [t for t in re.findall(r'[\u4e00-\u9fff]{1,3}|[a-zA-Z]+', text.lower()) if len(t) >= 1]

class HybridRetriever:
    """Hybrid retrieval: BM25 (keyword) + Vector (semantic) + Ontology (knowledge-guided).

    Sprint 6: Supports ChromaDB-accelerated vector search. Falls back to
    brute-force TF-IDF similarity when ChromaDB is unavailable.
    """

    def __init__(self, chunk_store: ChunkStore, embedding_gen,
                 ontology: Optional[OntologyGraph] = None,
                 vector_store=None):
        self.chunk_store = chunk_store
        self.embedding_gen = embedding_gen
        self.ontology = ontology
        self.vector_store = vector_store  # Optional ChromaVectorStore
        self.bm25 = BM25Scorer()
        self._chunk_list: List[Chunk] = []
        self._fitted = False

    def fit(self):
        self._chunk_list = self.chunk_store.all_chunks()
        texts = [c.content for c in self._chunk_list]
        self.bm25.fit(texts)

        # Fit embedding if needed (TF-IDF fallback requires fitting)
        if hasattr(self.embedding_gen, '_fitted'):
            if not self.embedding_gen._fitted:
                self.embedding_gen.fit(texts)
        else:
            # EmbeddingProvider — try fit if available
            if hasattr(self.embedding_gen, 'fit'):
                self.embedding_gen.fit(texts)

        # Index chunks in ChromaDB vector store if available
        if self.vector_store and self.vector_store.enabled and self._chunk_list:
            embed = self.embedding_gen
            embeddings = []
            if hasattr(embed, 'encode_batch_as_lists'):
                embeddings = embed.encode_batch_as_lists(texts)
            else:
                for chunk in self._chunk_list:
                    if chunk.embedding is not None:
                        embeddings.append(chunk.embedding.tolist())
                    else:
                        vec = embed.encode(chunk.content)
                        embeddings.append(vec.tolist())

            if embeddings:
                added = self.vector_store.add_chunks(self._chunk_list, embeddings)
                if added > 0:
                    import logging
                    logging.getLogger(__name__).info(
                        "Indexed %d chunks in ChromaDB", added)

        self._fitted = True

    def retrieve(self, query: str, top_k: int = 10,
                 ontology_context: Optional[List[str]] = None,
                 document_types: Optional[List[str]] = None,
                 bm25_weight: float = 0.4, vector_weight: float = 0.4,
                 ontology_boost: float = 0.2) -> List[Tuple[Chunk, float]]:
        if not self._fitted:
            self.fit()

        query_vec = self.embedding_gen.encode(query)

        # Expand query via ontology
        ontology_entities: Set[str] = set()
        if self.ontology and ontology_context:
            for entity_name in ontology_context:
                entities = self.ontology.lookup(entity_name)
                for e in entities:
                    ontology_entities.add(e.entity_id)
                    expanded = self.ontology.expand_context([e.entity_id], max_depth=1, max_results=10)
                    for ee in expanded:
                        ontology_entities.add(ee.entity_id)

        # Try ChromaDB-accelerated vector search first
        chroma_results: Dict[str, float] = {}
        if self.vector_store and self.vector_store.enabled:
            query_vec_list = query_vec.tolist() if isinstance(query_vec, np.ndarray) else query_vec
            chroma_hits = self.vector_store.search(query_vec_list, top_k=top_k * 3)
            for cid, score, _ in chroma_hits:
                chroma_results[cid] = score

        scores = []
        for i, chunk in enumerate(self._chunk_list):
            # Filter by document type if specified
            if document_types:
                doc_meta = self.chunk_store.get_document_meta(chunk.document_id)
                if doc_meta and doc_meta.document_type not in document_types:
                    continue

            bm25_score = self.bm25.score(query, i)

            # Vector score: prefer ChromaDB pre-computed score, fallback to brute-force
            if chunk.chunk_id in chroma_results:
                vector_score = chroma_results[chunk.chunk_id]
            else:
                chunk_vec = chunk.embedding if chunk.embedding is not None else self.embedding_gen.encode(chunk.content)
                if hasattr(self.embedding_gen, 'similarity'):
                    vector_score = self.embedding_gen.similarity(query_vec, chunk_vec)
                else:
                    from sklearn.metrics.pairwise import cosine_similarity
                    a = query_vec.reshape(1, -1)
                    b = chunk_vec.reshape(1, -1)
                    vector_score = float(cosine_similarity(a, b)[0][0])

            # Ontology boost
            onto_score = 0.0
            if ontology_entities and hasattr(chunk, 'metadata'):
                linked_entities = chunk.metadata.get('entity_links', [])
                overlap = len(set(linked_entities) & ontology_entities)
                if overlap > 0:
                    onto_score = min(overlap / len(ontology_entities), 0.3)

            total = bm25_weight * bm25_score + vector_weight * vector_score + ontology_boost * onto_score
            scores.append((chunk, total))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def retrieve_evidence(self, query: str, top_k: int = 10, **kwargs) -> List[Dict[str, Any]]:
        results = self.retrieve(query, top_k, **kwargs)
        return [{
            "chunk_id": c.chunk_id, "document_id": c.document_id,
            "content": c.content, "clause": c.clause,
            "score": round(s, 4), "source_type": "hybrid_retrieval"
        } for c, s in results]
