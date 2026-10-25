import unittest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
import json

import db
from app import app, ADMIN_PASSWORD
from ai_service import AIService, clean_student_reply

class Phase3Tests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_clean_student_reply(self):
        dirty = """NOT_IN_MATERIAL
Here is the legal provision for Section 115BAC.
Source: ICAI Module Chapter 4
Based on general knowledge
From the study material, Section 115BAC is default."""
        cleaned = clean_student_reply(dirty)
        self.assertNotIn("NOT_IN_MATERIAL", cleaned)
        self.assertNotIn("Source: ICAI", cleaned)
        self.assertNotIn("Based on general knowledge", cleaned)
        self.assertIn("Section 115BAC", cleaned)

    def test_api_chat_course_level_validation(self):
        # 1. Invalid course/level should return 400
        res = self.client.post("/api/chat", data={
            "message": "What is Section 115BAC?",
            "course": "InvalidCourse",
            "level": "InvalidLevel"
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("Invalid course/level", res.json().get("detail", ""))

    def test_api_chat_history_and_retrieval(self):
        # Mock cloud_store.query and ai.get_response
        mock_chunks = [
            {"subject": "Taxation", "content": "Section 115BAC default slab", "score": 0.85},
            {"subject": "Taxation", "content": "Section 115BAC deductions disallowed", "score": 0.50}  # Below 0.62 MIN_SCORE
        ]

        with patch("app.cloud_store.query", new_callable=AsyncMock, return_value=mock_chunks) as mock_query, \
             patch("app.ai.get_response", new_callable=AsyncMock) as mock_ai_resp:
            
            mock_ai_resp.return_value = {
                "reply": "Section 115BAC is the default concessional tax regime.",
                "source": "material",
                "top_score": 0.85,
                "model_used": "gemini-flash-latest"
            }

            history = [
                {"role": "user", "text": "Tell me about Section 115BAC."},
                {"role": "assistant", "text": "It is the default regime under Income Tax Act."}
            ]

            res = self.client.post("/api/chat", data={
                "message": "What about deductions under it?",
                "course": "CA",
                "level": "Inter",
                "history": json.dumps(history)
            })

            self.assertEqual(res.status_code, 200)
            data = res.json()
            # Student-facing reply MUST have "reply" key
            self.assertIn("reply", data)
            # Student MUST NOT see source or score
            self.assertNotIn("source", data)
            self.assertNotIn("top_score", data)

            # Check that Pinecone was queried in student's namespace: ca-inter
            call_args = mock_query.call_args
            self.assertEqual(call_args.kwargs.get("namespace"), "ca-inter")

            # Check that follow-up combined the query
            query_used = call_args.args[0]
            self.assertIn("Tell me about Section 115BAC.", query_used)
            self.assertIn("What about deductions under it?", query_used)

            # Check that only chunks with score >= 0.62 were passed to AI (1 chunk out of 2)
            ai_call_args = mock_ai_resp.call_args
            passed_chunks = ai_call_args.kwargs.get("context_chunks", [])
            self.assertEqual(len(passed_chunks), 1)
            self.assertEqual(passed_chunks[0]["score"], 0.85)

    def test_grounded_to_general_knowledge_fallback(self):
        ai = AIService(api_key="valid_test_api_key_12345")

        # Mock _call_gemini_api:
        # First call (grounded) returns NOT_IN_MATERIAL
        # Second call (general) returns the general knowledge answer
        mock_gemini = AsyncMock()
        mock_gemini.side_effect = [
            "NOT_IN_MATERIAL",
            "Under general corporate law, CSR applies to companies exceeding statutory thresholds."
        ]

        with patch.object(ai, "_call_gemini_api", mock_gemini):
            import asyncio
            chunks = [{"content": "Unrelated material", "score": 0.70}]
            res = asyncio.run(ai.get_response(
                message="What are CSR applicability thresholds?",
                context_chunks=chunks,
                course="CA",
                level="Inter"
            ))

            self.assertEqual(res["source"], "general")
            self.assertNotIn("NOT_IN_MATERIAL", res["reply"])
            self.assertIn("CSR applies", res["reply"])
            self.assertEqual(mock_gemini.call_count, 2)

    def test_image_question_extraction(self):
        ai = AIService(api_key="valid_test_api_key_12345")
        with patch.object(ai, "_call_gemini_api", new_callable=AsyncMock, return_value="Calculate Material Cost Variance from the given data"):
            import asyncio
            q_text = asyncio.run(ai.extract_question_from_image("fake_b64"))
            self.assertEqual(q_text, "Calculate Material Cost Variance from the given data")

if __name__ == "__main__":
    unittest.main()
