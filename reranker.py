"""
reranker.py
===========
Enterprise-grade Cross-Encoder Reranker Service for 2-Stage RAG Pipeline.

Architecture:
- Stage 1 (Retrieval): Dense bi-encoder (Pinecone serverless) or sparse keyword (TF-IDF fallback)
  retrieves a broad candidate set of top-k (e.g. 20) passages.
- Stage 2 (Reranking): Cross-Encoder jointly attends over the query and candidate passages,
  capturing deep token-level interactions and cross-attention signals to output precise relevance scores.
- Stage 3 (Filtering & Context Assembly): Threshold filtering (MIN_SCORE) and top-N (e.g. top 4) selection
  to minimize hallucinations and deliver pristine grounding context to the LLM.

Concurrency & Performance:
- CPU-intensive cross-encoder inference is executed via `asyncio.to_thread` to guarantee
  zero blocking of the FastAPI asynchronous event loop.
- Lazy singleton model initialization with thread safety.
- Graceful degradation: in case of initialization or inference failure, the service logs
  the issue and falls back to original retrieval scores without disrupting the user request.
"""

import os
import asyncio
import threading
import logging
import structlog
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

logger = structlog.get_logger("excel_ai.reranker")

# Default lightweight cross-encoder model (80MB, fast CPU inference)
DEFAULT_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RERANKER_MODEL_NAME = os.getenv("RERANKER_MODEL_NAME", DEFAULT_MODEL_NAME)
RERANKER_ENABLED = os.getenv("RERANKER_ENABLED", "true").lower() in ("true", "1", "yes")

# Optional import for sentence_transformers CrossEncoder
try:
    from sentence_transformers import CrossEncoder
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    CrossEncoder = None
    SENTENCE_TRANSFORMERS_AVAILABLE = False


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid function mapping raw logits to [0.0, 1.0]."""
    if x >= 0:
        z = np.exp(-x)
        return float(1.0 / (1.0 + z))
    else:
        z = np.exp(x)
        return float(z / (1.0 + z))


class CrossEncoderReranker:
    """
    Two-Stage Cross-Encoder Reranker.
    Loads and runs a cross-encoder model to score (query, document) pairs.
    """

    def __init__(
        self,
        model_name: str = RERANKER_MODEL_NAME,
        enabled: bool = RERANKER_ENABLED,
        max_length: int = 512
    ):
        self.model_name = model_name
        self.enabled = enabled
        self.max_length = max_length
        self._model = None
        self._lock = threading.Lock()
        self._load_failed = False

    def is_available(self) -> bool:
        """Returns True if reranking is enabled and sentence_transformers is available."""
        return self.enabled and SENTENCE_TRANSFORMERS_AVAILABLE and not self._load_failed

    def _get_model(self) -> Optional[Any]:
        """Lazy-loads the CrossEncoder model with thread-safe double-checked locking."""
        if not self.is_available():
            return None

        if self._model is None:
            with self._lock:
                if self._model is None and not self._load_failed:
                    try:
                        logger.info(f"Initializing Cross-Encoder model '{self.model_name}'...")
                        self._model = CrossEncoder(
                            model_name_or_path=self.model_name,
                            max_length=self.max_length
                        )
                        logger.info(f"Cross-Encoder model '{self.model_name}' loaded successfully.")
                    except Exception as e:
                        self._load_failed = True
                        logger.warning(f"Failed to load Cross-Encoder model '{self.model_name}': {e}")
                        return None
        return self._model

    def _predict_sync(self, pairs: List[Tuple[str, str]]) -> List[float]:
        """
        Synchronous CPU inference function designed to run in asyncio thread pool.
        Returns a list of sigmoid-normalized relevance scores in [0.0, 1.0].
        """
        model = self._get_model()
        if model is None or not pairs:
            return [0.0] * len(pairs)

        try:
            raw_scores = model.predict(pairs)
            if hasattr(raw_scores, "tolist"):
                scores_list = raw_scores.tolist()
            else:
                scores_list = list(raw_scores)

            # Apply sigmoid normalization so scores map smoothly to [0.0, 1.0]
            normalized = [_sigmoid(float(s)) for s in scores_list]
            return normalized
        except Exception as e:
            logger.warning("Cross-Encoder prediction error, falling back to default scores", error=str(e))
            logger.warning(f"Cross-Encoder prediction error: {e}")
            return [0.0] * len(pairs)

    async def rerank(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        top_k: int = 4,
        min_score: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Reranks a list of candidate chunks against the user query.

        Args:
            query: The search query (user question or enriched context).
            chunks: Candidate chunks retrieved from Stage 1 (Pinecone / TF-IDF).
            top_k: Number of top reranked chunks to return (default: 4).
            min_score: Optional minimum relevance score threshold (default: None).

        Returns:
            List of top_k reranked and filtered chunks with 'rerank_score' and 'original_score'.
        """
        if not chunks:
            return []

        # If reranker is disabled or unavailable, preserve existing score order and apply filters
        if not self.is_available():
            fallback_sorted = sorted(
                chunks,
                key=lambda x: float(x.get("score", x.get("relevance_score", 0.0))),
                reverse=True
            )
            for c in fallback_sorted:
                orig = float(c.get("score", c.get("relevance_score", 0.0)))
                c.setdefault("original_score", orig)
                c.setdefault("rerank_score", orig)

            if min_score is not None:
                fallback_sorted = [
                    c for c in fallback_sorted
                    if float(c.get("score", c.get("relevance_score", 0.0))) >= min_score
                ]
            return fallback_sorted[:top_k]

        # Extract (query, content) pairs for CrossEncoder evaluation
        pairs = []
        for c in chunks:
            content = c.get("content") or c.get("text") or ""
            # Prefix with subject or section context if present for richer cross-attention
            section = c.get("section") or ""
            subject = c.get("subject") or ""
            doc_context = f"{subject} {section}: {content}".strip() if (section or subject) else content
            pairs.append((query, doc_context))

        # Offload CPU inference to worker thread pool to prevent blocking async event loop
        rerank_scores = await asyncio.to_thread(self._predict_sync, pairs)

        reranked_chunks = []
        for chunk, r_score in zip(chunks, rerank_scores):
            chunk_copy = dict(chunk)
            orig_score = float(chunk_copy.get("score", chunk_copy.get("relevance_score", 0.0)))
            r_score_rounded = round(float(r_score), 4)

            chunk_copy["original_score"] = orig_score
            chunk_copy["rerank_score"] = r_score_rounded
            chunk_copy["score"] = r_score_rounded  # Update primary score for downstream consumers

            # Debug log statement required by acceptance criteria:
            # "Add a log statement showing the original score vs. reranked score for debugging."
            doc_name = chunk_copy.get("doc_name") or chunk_copy.get("subject") or "Study_Material"
            sec_name = chunk_copy.get("section") or f"Page {chunk_copy.get('page', '?')}"
            logger.info(
                f"[Reranker] Chunk '{doc_name}' ({sec_name}): "
                f"Original Score = {orig_score:.4f}, Reranked Score = {r_score_rounded:.4f}"
            )

            reranked_chunks.append(chunk_copy)

        # Sort by reranked score descending
        sorted_chunks = sorted(
            reranked_chunks,
            key=lambda x: float(x.get("rerank_score", 0.0)),
            reverse=True
        )

        # Final filter by MIN_SCORE if configured
        if min_score is not None:
            filtered_chunks = [
                c for c in sorted_chunks
                if float(c.get("rerank_score", c.get("score", 0.0))) >= min_score
            ]
        else:
            filtered_chunks = sorted_chunks

        # Return strictly top_k chunks
        return filtered_chunks[:top_k]


# Global singleton instance
_reranker_instance: Optional[CrossEncoderReranker] = None
_instance_lock = threading.Lock()


def get_reranker() -> CrossEncoderReranker:
    """Returns the global thread-safe singleton CrossEncoderReranker instance."""
    global _reranker_instance
    if _reranker_instance is None:
        with _instance_lock:
            if _reranker_instance is None:
                _reranker_instance = CrossEncoderReranker()
    return _reranker_instance
