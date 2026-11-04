"""
reranker.py  —  Lightweight Score-Based Reranker (Pass-Through)
================================================================
The local Cross-Encoder model (sentence-transformers / PyTorch) was removed because
it required ~500 MB of RAM and caused OOM crashes on 512 MB Render containers.

FUTURE UPGRADE PATH:
  Replace this shim with an async call to an external reranking API, e.g.:
  - Jina Reranker API  : https://jina.ai/reranker/
  - Cohere Rerank API  : https://docs.cohere.com/reference/rerank
  Both are pay-per-call, have no cold-start RAM cost, and require only `httpx`.

Current behaviour:
  Chunks from Pinecone / TF-IDF already arrive sorted by cosine-similarity score.
  This module simply applies the MIN_SCORE threshold and returns the top-k results,
  which mirrors the behaviour the cross-encoder provided on cache-misses / fallback.

Public API is preserved so app.py and tests require zero changes.
"""

import structlog
from typing import List, Dict, Any, Optional

logger = structlog.get_logger("excel_ai.reranker")

# Signals that no local model is loaded (kept for health-check endpoint compatibility).
RERANKER_ENABLED = False
DEFAULT_MODEL_NAME = "score-passthrough"


class CrossEncoderReranker:
    """
    Lightweight pass-through reranker.

    Accepts the same interface as the former Cross-Encoder class so that
    app.py and all existing tests continue to work without modification.

    Re-ranks by the existing retrieval score (cosine similarity from Pinecone
    or TF-IDF relevance from local RAGEngine), applies MIN_SCORE filtering,
    and returns the top-k chunks.

    To swap in a real API-based reranker later:
      1. Add `httpx` calls here to Jina / Cohere rerank endpoint.
      2. Replace the sort key below with the API-returned scores.
      3. Flip RERANKER_ENABLED = True in .env.
    """

    model_name: str = DEFAULT_MODEL_NAME

    def is_available(self) -> bool:
        """Returns False — no local model is loaded."""
        return False

    async def rerank(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        top_k: int = 4,
        min_score: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Sort chunks by their existing retrieval score, apply MIN_SCORE filter,
        and return top-k.  O(n log n), no I/O, no RAM overhead.
        """
        if not chunks:
            return []

        # Sort descending by whatever score key the upstream retriever stored.
        sorted_chunks = sorted(
            chunks,
            key=lambda c: float(c.get("score", c.get("relevance_score", 0.0))),
            reverse=True,
        )

        # Apply minimum relevance threshold if provided.
        if min_score is not None:
            sorted_chunks = [
                c for c in sorted_chunks
                if float(c.get("score", c.get("relevance_score", 0.0))) >= min_score
            ]

        result = sorted_chunks[:top_k]

        logger.info(
            "Pass-through reranker applied",
            query_preview=query[:60],
            candidates_in=len(chunks),
            chunks_out=len(result),
            top_score=float(result[0].get("score", 0.0)) if result else 0.0,
        )
        return result


# ---------------------------------------------------------------------------
# Global singleton — same factory function as before so imports stay identical
# ---------------------------------------------------------------------------
_reranker_instance: Optional[CrossEncoderReranker] = None


def get_reranker() -> CrossEncoderReranker:
    """Returns the global singleton CrossEncoderReranker (pass-through) instance."""
    global _reranker_instance
    if _reranker_instance is None:
        _reranker_instance = CrossEncoderReranker()
        logger.info(
            "Reranker initialised",
            mode="score-passthrough",
            note="Local cross-encoder disabled; using cosine-similarity ordering. "
                 "Swap for Jina/Cohere API when RAM budget allows.",
        )
    return _reranker_instance
