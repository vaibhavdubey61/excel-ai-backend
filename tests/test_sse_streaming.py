import unittest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from ai_service import AIService
import app


class TestSSEStreaming(unittest.IsolatedAsyncioTestCase):
    """Unit and integration tests for Server-Sent Events (SSE) streaming."""

    async def test_ai_service_stream_response_generator(self):
        """ai_service.stream_response yields tokens as an async generator."""
        ai = AIService(api_key="AIzaSyMockKeyForTesting12345")

        async def mock_stream_tokens(*args, **kwargs):
            tokens = ["Section ", "115BAC ", "provides ", "a concessional ", "tax regime."]
            for t in tokens:
                yield t

        with patch.object(ai, "_stream_llm", side_effect=mock_stream_tokens):
            collected = []
            async for token in ai.stream_response(
                message="What is Section 115BAC?",
                course="CA",
                level="Inter"
            ):
                collected.append(token)

            self.assertEqual("".join(collected), "Section 115BAC provides a concessional tax regime.")

    def test_api_chat_curl_sse_streaming(self):
        """Acceptance Criteria: curl -N http://localhost:8000/api/chat receives SSE text/event-stream with tokens."""
        client = TestClient(app.app)

        async def mock_stream_tokens(*args, **kwargs):
            tokens = ["According ", "to ", "Section ", "115BAC."]
            for t in tokens:
                yield t

        with patch("app.cloud_store.query", new_callable=AsyncMock, return_value=[]), \
             patch("app.reranker.rerank", new_callable=AsyncMock, return_value=[]), \
             patch.object(app.ai, "stream_response", side_effect=mock_stream_tokens), \
             patch("app.db.log_chat_interaction"):

            # Simulate curl -N request (User-Agent: curl/8.4.0)
            resp = client.post(
                "/api/chat",
                data={"message": "Explain Section 115BAC", "course": "CA", "level": "Inter"},
                headers={"User-Agent": "curl/8.4.0"}
            )

            self.assertEqual(resp.status_code, 200)
            self.assertIn("text/event-stream", resp.headers.get("content-type", ""))
            body = resp.text

            # Verify immediate "Searching knowledge base..." status event
            self.assertIn('{"event": "status", "message": "Searching knowledge base..."}', body)

            # Verify token chunks: data: {"token": "..."}\n\n
            self.assertIn('{"token": "According "}', body)
            self.assertIn('{"token": "Section "}', body)

            # Verify final done event
            self.assertIn('{"event": "done"', body)

    def test_api_chat_explicit_stream_param(self):
        """Passing stream='true' explicitly triggers SSE streaming."""
        client = TestClient(app.app)

        async def mock_stream_tokens(*args, **kwargs):
            tokens = ["Income ", "Tax ", "Rules."]
            for t in tokens:
                yield t

        with patch("app.cloud_store.query", new_callable=AsyncMock, return_value=[]), \
             patch("app.reranker.rerank", new_callable=AsyncMock, return_value=[]), \
             patch.object(app.ai, "stream_response", side_effect=mock_stream_tokens), \
             patch("app.db.log_chat_interaction"):

            resp = client.post(
                "/api/chat",
                data={"message": "Tell me the rules", "stream": "true"},
            )

            self.assertEqual(resp.status_code, 200)
            self.assertIn("text/event-stream", resp.headers.get("content-type", ""))
            self.assertIn('{"token": "Income "}', resp.text)
            self.assertIn('{"token": "Rules."}', resp.text)

    def test_api_chat_non_streaming_backward_compatibility(self):
        """Constraints: Do not break existing non-streaming admin/evaluation scripts."""
        client = TestClient(app.app)

        with patch("app.cloud_store.query", new_callable=AsyncMock, return_value=[]), \
             patch("app.reranker.rerank", new_callable=AsyncMock, return_value=[]), \
             patch("app.ai.get_response", new_callable=AsyncMock) as mock_get_resp, \
             patch("app.db.log_chat_interaction"):

            mock_get_resp.return_value = {
                "reply": "Standard non-streaming JSON reply for evaluation scripts.",
                "source": "general",
                "top_score": 0.0,
                "model_used": "gemini-flash"
            }

            # Standard testclient request without streaming
            resp = client.post(
                "/api/chat",
                data={"message": "Evaluate this test case", "course": "CA", "level": "Inter"}
            )

            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn("reply", data)
            self.assertEqual(data["reply"], "Standard non-streaming JSON reply for evaluation scripts.")


if __name__ == "__main__":
    unittest.main()
