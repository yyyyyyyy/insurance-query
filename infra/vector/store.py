"""
ChromaDB Vector Store — Persistent vector storage with metadata search.

Replaces the in-memory-only approach. Works alongside ChunkStore:
  - ChunkStore: document metadata + chunk registry (lightweight)
  - ChromaVectorStore: vector embeddings + similarity search (persistent)

If ChromaDB is not installed, falls back gracefully to in-memory mode.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from knowledge.ingestion.pipeline import Chunk

logger = logging.getLogger(__name__)


class ChromaVectorStore:
    """ChromaDB-backed vector store for insurance document chunks.

    Usage:
        store = ChromaVectorStore(persist_dir="./data/vectordb")
        store.add_chunks(chunks, embeddings)
        results = store.search(query_embedding, top_k=10)
    """

    def __init__(self, persist_dir: Optional[str] = None, collection_name: str = "insurance_chunks"):
        self.persist_dir = persist_dir or str(Path(__file__).resolve().parents[2] / "data" / "vectordb")
        self.collection_name = collection_name
        self._client = None
        self._collection = None
        self._enabled = False
        self._chunk_count = 0

        # Try to initialize ChromaDB
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            self._client = chromadb.PersistentClient(
                path=self.persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            # Get or create collection
            try:
                self._collection = self._client.get_collection(self.collection_name)
                self._chunk_count = self._collection.count()
                logger.info(
                    "ChromaDB initialized at %s, collection '%s' has %d chunks",
                    self.persist_dir, self.collection_name, self._chunk_count,
                )
            except Exception:
                self._collection = self._client.create_collection(
                    name=self.collection_name,
                    metadata={"description": "Insurance document chunks with vector embeddings"},
                )
                logger.info(
                    "ChromaDB collection '%s' created at %s",
                    self.collection_name, self.persist_dir,
                )
            self._enabled = True

        except ImportError:
            logger.warning(
                "ChromaDB not installed. Install with: pip install chromadb. "
                "Falling back to in-memory vector search."
            )
        except Exception as exc:
            logger.warning("ChromaDB initialization failed: %s. Falling back to in-memory.", exc)

    @property
    def enabled(self) -> bool:
        return self._enabled and self._collection is not None

    def add_chunks(
        self,
        chunks: List[Chunk],
        embeddings: List[List[float]],
    ) -> int:
        """Add chunks with embeddings to the vector store.

        Returns the number of chunks added.
        """
        if not self.enabled or not chunks:
            return 0

        ids = [c.chunk_id for c in chunks]
        documents = [c.content for c in chunks]
        metadatas = []
        for c in chunks:
            meta = {
                "document_id": c.document_id,
                "clause": c.clause,
                "chunk_index": c.chunk_index,
                "section_title": c.section_title,
            }
            if c.metadata:
                for k, v in c.metadata.items():
                    meta[f"meta_{k}"] = str(v)[:200]
            metadatas.append(meta)

        try:
            self._collection.add(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )
            self._chunk_count += len(chunks)
            logger.debug("Added %d chunks to ChromaDB", len(chunks))
            return len(chunks)
        except Exception as exc:
            logger.warning("Failed to add chunks to ChromaDB: %s", exc)
            return 0

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[str, float, Optional[Dict[str, Any]]]]:
        """Search for chunks by vector similarity.

        Returns list of (chunk_id, score, metadata) tuples.
        """
        if not self.enabled:
            return []

        try:
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, self._chunk_count),
                where=where,
                include=["metadatas", "distances"],
            )
            items = []
            if results["ids"] and results["ids"][0]:
                for i, cid in enumerate(results["ids"][0]):
                    dist = results["distances"][0][i] if results.get("distances") else 1.0
                    meta = results["metadatas"][0][i] if results.get("metadatas") else None
                    score = 1.0 - min(float(dist), 1.0)  # Convert distance to similarity
                    items.append((cid, score, meta))
            return items
        except Exception as exc:
            logger.warning("ChromaDB search failed: %s", exc)
            return []

    def get_by_document(self, document_id: str) -> List[Dict[str, Any]]:
        """Retrieve all chunks for a document."""
        if not self.enabled:
            return []
        try:
            result = self._collection.get(
                where={"document_id": document_id},
                include=["documents", "metadatas"],
            )
            return [
                {"chunk_id": rid, "content": doc, "metadata": meta}
                for rid, doc, meta in zip(
                    result.get("ids", []),
                    result.get("documents", []),
                    result.get("metadatas", []),
                )
            ]
        except Exception:
            return []

    def delete_document(self, document_id: str) -> int:
        """Delete all chunks belonging to a document."""
        if not self.enabled:
            return 0
        try:
            result = self._collection.get(
                where={"document_id": document_id},
                include=[],
            )
            ids = result.get("ids", [])
            if ids:
                self._collection.delete(ids=ids)
                deleted = len(ids)
                self._chunk_count -= deleted
                return deleted
            return 0
        except Exception:
            return 0

    def count(self) -> int:
        return self._chunk_count if self.enabled else 0

    def clear(self) -> None:
        """Clear all chunks from the collection."""
        if self.enabled:
            try:
                all_ids = self._collection.get(include=[])["ids"]
                if all_ids:
                    self._collection.delete(ids=all_ids)
                self._chunk_count = 0
            except Exception:
                pass

    def stats(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "chunk_count": self._chunk_count,
            "persist_dir": self.persist_dir,
            "collection": self.collection_name,
        }
