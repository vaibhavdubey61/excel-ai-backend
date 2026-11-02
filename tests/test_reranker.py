import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import numpy as np

from reranker import CrossEncoderReranker, _sigmoid, get_reranker


class TestCrossEncoderReranker(unittest.IsolatedAsyncioTestCase):
    """Unit tests for CrossEncoderReranker and 2-stage retrieval pipeline."""

    def test_sigmoid_math(self):
        """Test numerically stable sigmoid calculation."""
        self.assertAlmostEqual(_sigmoid(0.0), 0.5, places=4)
        self.assertGreater(_sigmoid(2.0), 0.85)
        self.assertLess(_sigmoid(-2.0), 0.15)
        self.assertAlmostEqual(_sigmoid(100.0), 1.0, places=4)
        self.assertAlmostEqual(_sigmoid(-100.0), 0.0, places=4)

    def test_singleton_get_reranker(self):
        """Verify get_reranker returns a singleton instance."""
        r1 = get_reranker()
        r2 = get_reranker()
        self.assertIs(r1, r2)
        self.assertIsInstance(r1, CrossEncoderReranker)

    async def test_rerank_empty_chunks(self):
        """Reranking empty list should immediately return empty list."""
        reranker = CrossEncoderReranker()
        result = await reranker.rerank(query="What is Section 115BAC?", chunks=[], top_k=4)
        self.assertEqual(result, [])

    async def test_rerank_disabled_fallback(self):
        """When reranker is disabled, falls back to original vector scores and applies min_score & top_k."""
        reranker = CrossEncoderReranker(enabled=False)
        self.assertFalse(reranker.is_available())

        chunks = [
            {"content": "Chunk A", "score": 0.40, "doc_name": "DocA"},
            {"content": "Chunk B", "score": 0.90, "doc_name": "DocB"},
            {"content": "Chunk C", "score": 0.75, "doc_name": "DocC"},
            {"content": "Chunk D", "score": 0.65, "doc_name": "DocD"},
            {"content": "Chunk E", "score": 0.80, "doc_name": "DocE"},
        ]

        # Top 2 with min_score 0.70
        results = await reranker.rerank(
            query="test query",
            chunks=chunks,
            top_k=2,
            min_score=0.70
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["content"], "Chunk B")
        self.assertEqual(results[1]["content"], "Chunk E")
        self.assertEqual(results[0]["original_score"], 0.90)
        self.assertEqual(results[0]["rerank_score"], 0.90)

    async def test_rerank_scoring_and_sorting(self):
        """Verify cross-encoder scores candidate chunks, sorts descending, and caps at top_k."""
        reranker = CrossEncoderReranker(enabled=True)

        # 6 candidate chunks with various initial vector scores
        candidate_chunks = [
            {"content": "Low relevance chunk", "score": 0.88, "doc_name": "Doc1", "section": "Sec 1"},
            {"content": "Exact match for Section 115BAC slabs", "score": 0.65, "doc_name": "Doc2", "section": "Sec 2"},
            {"content": "Medium relevance chunk", "score": 0.70, "doc_name": "Doc3", "section": "Sec 3"},
            {"content": "High relevance chunk about rebates under 87A", "score": 0.66, "doc_name": "Doc4", "section": "Sec 4"},
            {"content": "Irrelevant chunk about GST filing", "score": 0.64, "doc_name": "Doc5", "section": "Sec 5"},
            {"content": "Another high relevance chunk", "score": 0.63, "doc_name": "Doc6", "section": "Sec 6"},
        ]

        # Mock _predict_sync to return specific calibrated scores
        # Note order corresponds to candidate_chunks
        mock_scores = [0.45, 0.96, 0.72, 0.91, 0.30, 0.84]

        with patch.object(reranker, "_predict_sync", return_value=mock_scores):
            with patch.object(reranker, "is_available", return_value=True):
                reranked = await reranker.rerank(
                    query="What are the Section 115BAC slabs?",
                    chunks=candidate_chunks,
                    top_k=4,
                    min_score=0.62
                )

        # Strictly top 4 chunks
        self.assertEqual(len(reranked), 4)

        # Verify sorted by rerank_score descending
        self.assertEqual(reranked[0]["content"], "Exact match for Section 115BAC slabs")
        self.assertEqual(reranked[0]["rerank_score"], 0.96)
        self.assertEqual(reranked[0]["original_score"], 0.65)
        self.assertEqual(reranked[0]["score"], 0.96)

        self.assertEqual(reranked[1]["content"], "High relevance chunk about rebates under 87A")
        self.assertEqual(reranked[1]["rerank_score"], 0.91)

        self.assertEqual(reranked[2]["content"], "Another high relevance chunk")
        self.assertEqual(reranked[2]["rerank_score"], 0.84)

        self.assertEqual(reranked[3]["content"], "Medium relevance chunk")
        self.assertEqual(reranked[3]["rerank_score"], 0.72)

        # Verify filtered out chunks:
        # "Low relevance chunk" had r_score 0.45 (< 0.62 min_score)
        # "Irrelevant chunk" had r_score 0.30 (< 0.62 min_score)
        contents = [c["content"] for c in reranked]
        self.assertNotIn("Low relevance chunk", contents)
        self.assertNotIn("Irrelevant chunk about GST filing", contents)

    async def test_rerank_graceful_inference_error_handling(self):
        """Verify _predict_sync handles model exceptions without crashing."""
        reranker = CrossEncoderReranker(enabled=True)
        mock_model = MagicMock()
        mock_model.predict.side_effect = RuntimeError("CUDA OOM / PyTorch error")

        with patch.object(reranker, "_get_model", return_value=mock_model):
            scores = reranker._predict_sync([("query", "chunk1"), ("query", "chunk2")])
            self.assertEqual(scores, [0.0, 0.0])

    async def test_api_chat_two_stage_retrieval_flow(self):
        """Integration test: Verify /api/chat retrieves top 20, reranks, and gives strictly top 4 to LLM."""
        from fastapi.testclient import TestClient
        import app

        client = TestClient(app.app)

        # Create 20 mock candidate chunks
        twenty_candidates = [
            {
                "id": f"chunk-{i}",
                "content": f"Passage content number {i} regarding Income Tax Act.",
                "score": 0.60 + (i * 0.01),
                "doc_name": f"Module_{i}",
                "section": f"Section {i}",
                "subject": "Taxation"
            }
            for i in range(20)
        ]

        # Top 4 reranked chunks returned by reranker
        reranked_top_4 = [
            {
                "id": "chunk-19",
                "content": "Top reranked chunk 1",
                "score": 0.98,
                "rerank_score": 0.98,
                "original_score": 0.79,
                "doc_name": "Module_19",
                "section": "Section 19",
                "subject": "Taxation"
            },
            {
                "id": "chunk-18",
                "content": "Top reranked chunk 2",
                "score": 0.95,
                "rerank_score": 0.95,
                "original_score": 0.78,
                "doc_name": "Module_18",
                "section": "Section 18",
                "subject": "Taxation"
            },
            {
                "id": "chunk-17",
                "content": "Top reranked chunk 3",
                "score": 0.92,
                "rerank_score": 0.92,
                "original_score": 0.77,
                "doc_name": "Module_17",
                "section": "Section 17",
                "subject": "Taxation"
            },
            {
                "id": "chunk-16",
                "content": "Top reranked chunk 4",
                "score": 0.89,
                "rerank_score": 0.89,
                "original_score": 0.76,
                "doc_name": "Module_16",
                "section": "Section 16",
                "subject": "Taxation"
            },
        ]

        with patch("app.cloud_store.query", new_callable=AsyncMock) as mock_query, \
             patch("app.reranker.rerank", new_callable=AsyncMock) as mock_rerank, \
             patch("app.ai.get_response", new_callable=AsyncMock) as mock_ai_response, \
             patch("app.db.log_chat_interaction"):

            mock_query.return_value = twenty_candidates
            mock_rerank.return_value = reranked_top_4
            mock_ai_response.return_value = {
                "reply": "According to Section 115BAC, rates are applicable as follows.",
                "source": "grounded",
                "top_score": 0.98,
                "model_used": "gemini-2.5-flash"
            }

            resp = client.post(
                "/api/chat",
                data={
                    "message": "Explain Section 115BAC tax slabs",
                    "course": "CA",
                    "level": "Inter"
                }
            )

            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn("Section 115BAC", data["reply"])

            # Verify Stage 1 fetched top 20
            mock_query.assert_called_once()
            _, query_kwargs = mock_query.call_args
            self.assertEqual(query_kwargs.get("top_k"), 20)

            # Verify Stage 2 received all 20 candidate chunks
            mock_rerank.assert_called_once()
            _, rerank_kwargs = mock_rerank.call_args
            self.assertEqual(len(rerank_kwargs.get("chunks")), 20)
            self.assertEqual(rerank_kwargs.get("top_k"), 4)

            # Verify Stage 3 passed strictly the reranked top 4 chunks to LLM
            mock_ai_response.assert_called_once()
            _, ai_kwargs = mock_ai_response.call_args
            self.assertEqual(len(ai_kwargs.get("context_chunks")), 4)
            self.assertEqual(ai_kwargs.get("context_chunks")[0]["id"], "chunk-19")
            self.assertEqual(ai_kwargs.get("context_chunks")[0]["rerank_score"], 0.98)


if __name__ == "__main__":
    unittest.main()
