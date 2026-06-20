"""
Knowledge Ingestion Pipeline — InsureQuery Runtime Sprint 3.

ARCHITECTURE:
    Raw Document (PDF/Text)
    → Text Extractor
    → Clause-aware Chunker
    → Embedding Generator
    → Chunk Store (vector + relational)

SPRINT 3 RULE: Knowledge Layer is source of truth.
Every ingested chunk must be traceable to its source document and clause.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# ============================================================
# Data Models
# ============================================================

@dataclass
class DocumentMeta:
    """Metadata for an ingested document."""
    document_id: str
    title: str
    source_path: str
    document_type: str  # policy_clause | regulation | claim_procedure
    file_type: str = "text"
    total_pages: int = 0
    product_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    """A semantically coherent chunk of document text."""
    chunk_id: str
    document_id: str
    content: str
    page: Optional[int] = None
    clause: str = ""
    section_title: str = ""
    chunk_index: int = 0
    embedding: Optional[np.ndarray] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "content": self.content,
            "page": self.page,
            "clause": self.clause,
            "section_title": self.section_title,
            "chunk_index": self.chunk_index,
            "metadata": self.metadata,
        }

    def embedding_list(self) -> Optional[List[float]]:
        if self.embedding is not None:
            return self.embedding.tolist()
        return None


# ============================================================
# Text Extraction
# ============================================================

def extract_text_from_file(file_path: str) -> Tuple[str, Dict[str, Any]]:
    """Extract raw text from a file (PDF or plain text)."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if path.suffix.lower() == '.pdf':
        return _extract_pdf_text(str(path))
    elif path.suffix.lower() in ('.txt', '.md', '.json'):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read(), {"file_type": path.suffix[1:]}
    else:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read(), {"file_type": path.suffix[1:]}


def _extract_pdf_text(file_path: str) -> Tuple[str, Dict[str, Any]]:
    """Extract text from PDF. Uses PyPDF2 if available, else reads as binary."""
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(file_path)
        text_parts = []
        for page in reader.pages:
            text_parts.append(page.extract_text() or "")
        return "\n\n".join(text_parts), {"file_type": "pdf", "pages": len(reader.pages)}
    except ImportError:
        # Fallback: treat as text (useful for testing with text files)
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return content, {"file_type": "pdf_no_parser", "pages": 1}


# ============================================================
# Clause-Aware Text Chunking
# ============================================================

# Clause patterns for Chinese insurance documents
CLAUSE_PATTERN = re.compile(
    r'(第[一二三四五六七八九十百千\d]+[章节条]|第[\d]+\.\d+条|[①②③④⑤⑥⑦⑧⑨⑩]\s*[、.)])'
)

SECTION_PATTERN = re.compile(
    r'(第[一二三四五六七八九十百千\d]+章|第[一二三四五六七八九十百千\d]+节|第[一二三四五六七八九十百千\d]+部分)'
)


def chunk_document(
    text: str,
    document_id: str,
    metadata: Optional[Dict[str, Any]] = None,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> List[Chunk]:
    """Split document text into semantically-aware chunks.

    Strategy:
    1. Split by clause boundaries first (preferred)
    2. If no clause boundaries found, split by paragraph/section
    3. If chunks are too long, further split by character with overlap

    Each chunk retains its clause number for traceability.
    """
    clauses = _split_by_clause(text)
    chunks = []
    chunk_idx = 0

    for clause_no, clause_text in clauses:
        # Clean whitespace
        clause_text = re.sub(r'\s+', ' ', clause_text).strip()
        if len(clause_text) < 20:
            continue

        # Split long clauses into sub-chunks with overlap
        if len(clause_text) > chunk_size * 1.5:
            sub_chunks = _split_long_text(clause_text, chunk_size, chunk_overlap)
            for sc in sub_chunks:
                chunks.append(Chunk(
                    chunk_id=f"{document_id}-C{chunk_idx:03d}",
                    document_id=document_id,
                    content=sc,
                    clause=clause_no,
                    chunk_index=chunk_idx,
                    metadata=metadata or {},
                ))
                chunk_idx += 1
        else:
            chunks.append(Chunk(
                chunk_id=f"{document_id}-C{chunk_idx:03d}",
                document_id=document_id,
                content=clause_text,
                clause=clause_no,
                chunk_index=chunk_idx,
                metadata=metadata or {},
            ))
            chunk_idx += 1

    return chunks


def _split_by_clause(text: str) -> List[Tuple[str, str]]:
    """Split text by clause boundaries. Returns list of (clause_number, text)."""
    matches = list(CLAUSE_PATTERN.finditer(text))

    if not matches:
        # No clause markers found — split by double newline
        paras = [p.strip() for p in text.split('\n\n') if p.strip()]
        return [(f"¶{i+1}", p) for i, p in enumerate(paras)]

    clauses = []
    # Text before first clause
    if matches[0].start() > 0:
        pre_text = text[:matches[0].start()].strip()
        if pre_text:
            clauses.append(("前文", pre_text))

    for i, m in enumerate(matches):
        clause_no = m.group(1).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        clause_text = text[start:end].strip()
        clauses.append((clause_no, clause_text))

    return clauses


def _split_long_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Split a long text into overlapping chunks of approximately chunk_size characters."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        # Try to break at sentence boundary
        if end < len(text):
            for sep in '。！？\n':
                last_sep = text.rfind(sep, start, end)
                if last_sep > start + chunk_size // 2:
                    end = last_sep + 1
                    break
        chunks.append(text[start:end].strip())
        start = end - overlap
    return chunks


# ============================================================
# Embedding Generator
# ============================================================

class EmbeddingGenerator:
    """Generate embeddings for text chunks.

    Sprint 3 uses TF-IDF as a deterministic, lightweight embedding.
    Falls back to hash-based encoding for very short corpora.
    """

    def __init__(self, vector_dim: int = 256):
        self.vector_dim = vector_dim
        self.vectorizer: Optional[TfidfVectorizer] = None
        self._fitted = False
        self._fallback = False

    def fit(self, texts: List[str]) -> "EmbeddingGenerator":
        """Fit the vectorizer on a corpus of texts."""
        if len(texts) < 3 or all(len(t) < 20 for t in texts[:5]):
            self._fallback = True
            self._fitted = True
            return self

        try:
            self.vectorizer = TfidfVectorizer(
                max_features=self.vector_dim,
                analyzer='char_wb',
                ngram_range=(2, 4),
                sublinear_tf=True,
            )
            self.vectorizer.fit(texts)
        except (ValueError, Exception):
            self._fallback = True

        self._fitted = True
        return self

    def encode(self, text: str) -> np.ndarray:
        """Generate embedding for a single text."""
        if not self._fitted:
            raise RuntimeError("EmbeddingGenerator not fitted. Call fit() first.")
        if self._fallback:
            return self._hash_embed(text)
        vec = self.vectorizer.transform([text]).toarray()[0]
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def _hash_embed(self, text: str) -> np.ndarray:
        """Fallback: deterministic hash-based embedding."""
        import hashlib
        vec = np.zeros(self.vector_dim, dtype=np.float64)
        for i, ch in enumerate(text):
            h = int(hashlib.md5(ch.encode()).hexdigest()[:8], 16)
            idx = (h + i * 31) % self.vector_dim
            vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def encode_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Generate embeddings for a batch of texts."""
        return [self.encode(t) for t in texts]

    def similarity(self, vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        a = vec_a.reshape(1, -1)
        b = vec_b.reshape(1, -1)
        return float(cosine_similarity(a, b)[0][0])


# ============================================================
# Chunk Store
# ============================================================

class ChunkStore:
    """Store for document chunks with retrieval capabilities.

    Maintains:
      - In-memory chunk index
      - Document metadata registry
      - Ability to persist/load to disk
    """

    def __init__(self):
        self._chunks: Dict[str, Chunk] = {}
        self._documents: Dict[str, DocumentMeta] = {}
        self._doc_chunks: Dict[str, List[str]] = {}  # document_id -> [chunk_ids]

    def add_chunk(self, chunk: Chunk) -> None:
        self._chunks[chunk.chunk_id] = chunk
        if chunk.document_id not in self._doc_chunks:
            self._doc_chunks[chunk.document_id] = []
        self._doc_chunks[chunk.document_id].append(chunk.chunk_id)

    def add_document(self, meta: DocumentMeta) -> None:
        self._documents[meta.document_id] = meta

    def get_chunk(self, chunk_id: str) -> Optional[Chunk]:
        return self._chunks.get(chunk_id)

    def get_document_chunks(self, document_id: str) -> List[Chunk]:
        chunk_ids = self._doc_chunks.get(document_id, [])
        return [self._chunks[cid] for cid in chunk_ids if cid in self._chunks]

    def get_document_meta(self, document_id: str) -> Optional[DocumentMeta]:
        return self._documents.get(document_id)

    def all_chunks(self) -> List[Chunk]:
        return list(self._chunks.values())

    def all_documents(self) -> List[DocumentMeta]:
        return list(self._documents.values())

    def chunk_count(self) -> int:
        return len(self._chunks)

    def document_count(self) -> int:
        return len(self._documents)

    def get_chunk_texts(self) -> List[str]:
        return [c.content for c in self._chunks.values()]

    def search_by_clause(self, document_id: str, clause: str) -> List[Chunk]:
        chunks = self.get_document_chunks(document_id)
        return [c for c in chunks if clause in c.clause]

    def to_serializable(self) -> Dict[str, Any]:
        return {
            "chunks": {cid: c.to_dict() for cid, c in self._chunks.items()},
            "documents": {
                did: {
                    "document_id": d.document_id,
                    "title": d.title,
                    "source_path": d.source_path,
                    "document_type": d.document_type,
                    "file_type": d.file_type,
                    "total_pages": d.total_pages,
                    "product_id": d.product_id,
                }
                for did, d in self._documents.items()
            },
            "doc_chunks": self._doc_chunks,
        }

    def save(self, path: str) -> None:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_serializable(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "ChunkStore":
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        store = cls()
        for cid, cdata in data["chunks"].items():
            chunk = Chunk(
                chunk_id=cdata["chunk_id"],
                document_id=cdata["document_id"],
                content=cdata["content"],
                page=cdata.get("page"),
                clause=cdata.get("clause", ""),
                section_title=cdata.get("section_title", ""),
                chunk_index=cdata.get("chunk_index", 0),
                metadata=cdata.get("metadata", {}),
            )
            store._chunks[cid] = chunk
        for did, ddata in data["documents"].items():
            store._documents[did] = DocumentMeta(**ddata)
        store._doc_chunks = data.get("doc_chunks", {})
        return store


# ============================================================
# Full Ingestion Pipeline
# ============================================================

def ingest_document(
    file_path: str,
    document_id: str,
    title: str,
    document_type: str,
    chunk_store: ChunkStore,
    embedding_gen: Optional[EmbeddingGenerator] = None,
    product_id: Optional[str] = None,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> Tuple[DocumentMeta, List[Chunk]]:
    """Full ingestion pipeline for a single document.

    Pipeline: Load → Extract → Chunk → Embed → Store
    """
    # Step 1: Extract text
    raw_text, file_info = extract_text_from_file(file_path)

    # Step 2: Register document metadata
    meta = DocumentMeta(
        document_id=document_id,
        title=title,
        source_path=file_path,
        document_type=document_type,
        file_type=file_info.get("file_type", "text"),
        total_pages=file_info.get("pages", 1),
        product_id=product_id,
    )
    chunk_store.add_document(meta)

    # Step 3: Chunk
    chunks = chunk_document(raw_text, document_id, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    # Step 4: Generate embeddings (if generator provided)
    if embedding_gen is not None:
        texts = [c.content for c in chunks]
        if not embedding_gen._fitted:
            all_texts = chunk_store.get_chunk_texts() + texts
            embedding_gen.fit(all_texts)
        embeddings = embedding_gen.encode_batch(texts)
        for chunk, emb in zip(chunks, embeddings):
            chunk.embedding = emb

    # Step 5: Store
    for chunk in chunks:
        chunk_store.add_chunk(chunk)

    return meta, chunks


def ingest_text_document(
    text: str,
    document_id: str,
    title: str,
    document_type: str,
    chunk_store: ChunkStore,
    embedding_gen: Optional[EmbeddingGenerator] = None,
    product_id: Optional[str] = None,
) -> Tuple[DocumentMeta, List[Chunk]]:
    """Ingest a text string directly (for programmatic use)."""
    meta = DocumentMeta(
        document_id=document_id,
        title=title,
        source_path=f"memory://{document_id}",
        document_type=document_type,
        file_type="inline",
        total_pages=1,
        product_id=product_id,
    )
    chunk_store.add_document(meta)

    chunks = chunk_document(text, document_id)
    if embedding_gen is not None:
        if not embedding_gen._fitted:
            embedding_gen.fit(chunk_store.get_chunk_texts() + [c.content for c in chunks])
        embeddings = embedding_gen.encode_batch([c.content for c in chunks])
        for chunk, emb in zip(chunks, embeddings):
            chunk.embedding = emb

    for chunk in chunks:
        chunk_store.add_chunk(chunk)

    return meta, chunks
