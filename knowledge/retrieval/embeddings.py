"""
Production Embedding Generator — sentence-transformers with TF-IDF fallback.

Primary: sentence-transformers (BAAI/bge-small-zh-v1.5 for Chinese)
Fallback: TF-IDF (char n-gram) from knowledge.ingestion.pipeline.EmbeddingGenerator

Usage:
    gen = EmbeddingFactory.create()
    vec = gen.encode("e生保的免赔额是多少")
"""
from __future__ import annotations

import logging
import os
from typing import List

import numpy as np

from knowledge.ingestion.pipeline import EmbeddingGenerator as TFIDFEmbedding

logger = logging.getLogger(__name__)


class SentenceTransformerEmbedding:
    """sentence-transformers based embedding for Chinese insurance text."""

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        self.model_name = model_name
        self._model = None
        self._enabled = False
        self._dim = 512  # default for bge-small-zh-v1.5
        self._init_model()

    def _init_model(self):
        if os.environ.get("EMBEDDING_FAST_MODE", "").lower() in ("1", "true"):
            logger.info("EMBEDDING_FAST_MODE=1, skipping sentence-transformers load")
            return
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            self._dim = (self._model.get_embedding_dimension()
                          if hasattr(self._model, 'get_embedding_dimension')
                          else self._model.get_sentence_embedding_dimension())
            self._enabled = True
            logger.info(
                "sentence-transformers loaded: model=%s dim=%d",
                self.model_name, self._dim,
            )
        except ImportError:
            logger.warning(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers. "
                "Falling back to TF-IDF embeddings."
            )
        except Exception as exc:
            logger.warning("Failed to load model %s: %s", self.model_name, exc)

    @property
    def enabled(self) -> bool:
        return self._enabled and self._model is not None

    @property
    def dimension(self) -> int:
        return self._dim

    def encode(self, text: str) -> np.ndarray:
        """Encode a single text to embedding vector."""
        if not self.enabled:
            raise RuntimeError("SentenceTransformerEmbedding not available")
        model = self._model
        if model is None:
            raise RuntimeError("SentenceTransformerEmbedding model not loaded")
        vec = model.encode(text, normalize_embeddings=True)
        return np.array(vec, dtype=np.float64)

    def encode_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Encode a batch of texts."""
        if not self.enabled:
            raise RuntimeError("SentenceTransformerEmbedding not available")
        model = self._model
        if model is None:
            raise RuntimeError("SentenceTransformerEmbedding model not loaded")
        embeddings = model.encode(texts, normalize_embeddings=True)
        return [np.array(e, dtype=np.float64) for e in embeddings]

    def encode_as_list(self, text: str) -> List[float]:
        """Encode text and return as plain Python list (for ChromaDB)."""
        vec = self.encode(text)
        return vec.tolist()

    def encode_batch_as_lists(self, texts: List[str]) -> List[List[float]]:
        """Batch encode and return as Python lists."""
        vecs = self.encode_batch(texts)
        return [v.tolist() for v in vecs]

    @staticmethod
    def similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        """Cosine similarity between two normalized vectors."""
        a = vec_a.reshape(1, -1)
        b = vec_b.reshape(1, -1)
        from sklearn.metrics.pairwise import cosine_similarity
        return float(cosine_similarity(a, b)[0][0])


class EmbeddingFactory:
    """Factory that selects the best available embedding method.

    Priority: sentence-transformers > TF-IDF
    """

    @staticmethod
    def create() -> "EmbeddingProvider":
        """Create the best available embedding provider."""
        st = SentenceTransformerEmbedding()
        if st.enabled:
            return EmbeddingProvider(primary=st, fallback=TFIDFEmbedding(vector_dim=st.dimension))
        else:
            tfidf = TFIDFEmbedding(vector_dim=384)
            return EmbeddingProvider(primary=tfidf, fallback=None)


class EmbeddingProvider:
    """Unified embedding interface with automatic fallback.

    Wraps a primary and fallback encoder with a common interface.
    Matches both the old EmbeddingGenerator and new sentence-transformers APIs.
    """

    def __init__(self, primary, fallback=None):
        self._primary = primary
        self._fallback = fallback
        self.__fitted = True  # pre-trained models are ready
        self._use_fallback = not getattr(primary, 'enabled', True)

    @property
    def vector_dim(self) -> int:
        if hasattr(self._primary, 'dimension'):
            return self._primary.dimension
        if hasattr(self._primary, 'vector_dim'):
            return self._primary.vector_dim
        return 512

    @property
    def _fitted(self) -> bool:
        """Compatibility with old EmbeddingGenerator API."""
        if self._primary is None:
            return False
        if hasattr(self._primary, '_fitted'):
            return self._primary._fitted
        return self.__fitted

    @property
    def using_sentence_transformer(self) -> bool:
        return isinstance(self._primary, SentenceTransformerEmbedding) and self._primary.enabled

    def encode(self, text: str) -> np.ndarray:
        if self._use_fallback and self._fallback:
            if not getattr(self._fallback, '_fitted', False):
                self._fallback.fit([text])
            return self._fallback.encode(text)
        try:
            primary = self._primary
            # Auto-fit TF-IDF primary if needed
            if hasattr(primary, '_fitted') and not primary._fitted:
                primary.fit([text])
            return primary.encode(text)
        except Exception as exc:
            logger.warning("Primary encoder failed: %s, using fallback", exc)
            if self._fallback:
                if not getattr(self._fallback, '_fitted', False):
                    self._fallback.fit([text])
                return self._fallback.encode(text)
            raise

    def encode_as_list(self, text: str) -> List[float]:
        """Encode to plain list (for ChromaDB)."""
        if hasattr(self._primary, 'encode_as_list'):
            try:
                return self._primary.encode_as_list(text)
            except Exception:
                pass
        vec = self.encode(text)
        return vec.tolist()

    def encode_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Encode a batch of texts (compatible with EmbeddingGenerator API)."""
        if self._use_fallback and self._fallback:
            if not getattr(self._fallback, '_fitted', False):
                self._fallback.fit(texts)
            if hasattr(self._fallback, 'encode_batch'):
                return self._fallback.encode_batch(texts)
            return [self._fallback.encode(t) for t in texts]
        try:
            # Auto-fit primary if needed
            if hasattr(self._primary, '_fitted') and not self._primary._fitted:
                self._primary.fit(texts)
            if hasattr(self._primary, 'encode_batch'):
                return self._primary.encode_batch(texts)
            return [self._primary.encode(t) for t in texts]
        except Exception:
            if self._fallback:
                if not getattr(self._fallback, '_fitted', False):
                    self._fallback.fit(texts)
                if hasattr(self._fallback, 'encode_batch'):
                    return self._fallback.encode_batch(texts)
                return [self._fallback.encode(t) for t in texts]
            raise

    def encode_batch_as_lists(self, texts: List[str]) -> List[List[float]]:
        """Batch encode to plain lists."""
        if hasattr(self._primary, 'encode_batch_as_lists'):
            try:
                return self._primary.encode_batch_as_lists(texts)
            except Exception:
                pass
        vecs = self._primary.encode_batch(texts) if hasattr(self._primary, 'encode_batch') else [self.encode(t) for t in texts]
        return [v.tolist() if isinstance(v, np.ndarray) else v for v in vecs]

    @staticmethod
    def similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        from sklearn.metrics.pairwise import cosine_similarity
        a = vec_a.reshape(1, -1)
        b = vec_b.reshape(1, -1)
        return float(cosine_similarity(a, b)[0][0])

    def fit(self, texts: List[str]) -> "EmbeddingProvider":
        """Fit encoders that need fitting (TF-IDF primary or fallback)."""
        if self._primary and hasattr(self._primary, 'fit') and not getattr(self._primary, '_fitted', True):
            self._primary.fit(texts)
        if self._fallback and not getattr(self._fallback, '_fitted', True):
            self._fallback.fit(texts)
        return self
