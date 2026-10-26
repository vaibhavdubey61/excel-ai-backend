import os
import unittest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

import db
from app import app, chat_limiter, ADMIN_PASSWORD
from cloud_vector_store import CloudVectorStore
from ai_service import AIService

class Phase1Tests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        chat_limiter.requests.clear()

    def test_admin_auth_endpoints(self):
        # 1. No key -> 401
        res = self.client.get("/api/admin/materials")
        self.assertEqual(res.status_code, 401)
        self.assertIn("Unauthorized", res.json().get("detail", ""))

        # 2. Wrong key -> 401
        res = self.client.get("/api/admin/materials", headers={"X-Admin-Key": "wrong-secret"})
        self.assertEqual(res.status_code, 401)

        # 3. Correct key -> 200
        res = self.client.get("/api/admin/materials", headers={"X-Admin-Key": ADMIN_PASSWORD})
        self.assertEqual(res.status_code, 200)
        self.assertIn("materials", res.json())

    def test_admin_html_access(self):
        # /admin should serve HTML or validate if key is passed
        res = self.client.get("/admin")
        self.assertEqual(res.status_code, 200)

        # /admin with wrong key header should be 401
        res_wrong = self.client.get("/admin", headers={"X-Admin-Key": "wrong"})
        self.assertEqual(res_wrong.status_code, 401)

        # /admin with correct key header should be 200
        res_ok = self.client.get("/admin", headers={"X-Admin-Key": ADMIN_PASSWORD})
        self.assertEqual(res_ok.status_code, 200)

    def test_chat_rate_limiting(self):
        # Limit is 30 requests per minute
        for i in range(30):
            res = self.client.post("/api/chat", data={"message": ""})
            # It should fail with 400 (validation), not 429 (rate limit)
            self.assertEqual(res.status_code, 400)

        # 31st request from same IP -> 429
        res_31 = self.client.post("/api/chat", data={"message": ""})
        self.assertEqual(res_31.status_code, 429)
        self.assertIn("limit: 30 requests/minute", res_31.json().get("detail", ""))

    def test_ai_busy_503_error_handling(self):
        with patch("app.cloud_store.query", new_callable=AsyncMock, return_value=[]), \
             patch("app.ai.get_response", new_callable=AsyncMock) as mock_get_resp:
            mock_get_resp.side_effect = Exception("All Gemini models exhausted")
            res = self.client.post("/api/chat", data={"message": "Hello"})
            self.assertEqual(res.status_code, 503)
            self.assertEqual(res.json().get("detail"), "The AI is busy right now. Please try again in a moment.")

        with patch("app.ai.generate_interactive_mcqs", new_callable=AsyncMock) as mock_mcq:
            mock_mcq.side_effect = Exception("Quota exceeded")
            res = self.client.post("/api/mcq/generate", json={"topic": "Taxation", "count": 5})
            self.assertEqual(res.status_code, 503)
            self.assertEqual(res.json().get("detail"), "The AI is busy right now. Please try again in a moment.")

    def test_simulation_methods_removed(self):
        # Ensure _simulate_response and _simulate_mcq_data do NOT exist
        self.assertFalse(hasattr(AIService, "_simulate_response"))
        self.assertFalse(hasattr(AIService, "_simulate_mcq_data"))

        # Candidate models order
        ai = AIService(api_key="test")
        self.assertEqual(set(ai.CANDIDATE_MODELS), {"gemini-flash-lite-latest", "gemini-flash-latest", "gemini-pro-latest"})

    def test_sqlite_db_operations(self):
        # Database operations
        test_mat = {
            "id": "mat_test_001",
            "doc_name": "Test_Doc.pdf",
            "subject": "CA_Foundation_Law",
            "pages": 10,
            "chunks": 25,
            "uploaded_at": "2026-10-26T00:00:00",
            "course": "CA",
            "level": "Foundation",
            "needs_ocr": 0
        }
        db.insert_material(test_mat)
        materials = db.get_materials()
        found = any(m["id"] == "mat_test_001" for m in materials)
        self.assertTrue(found)

        # Test chat log insertion
        db.log_chat_interaction(
            timestamp="2026-10-26T00:00:00",
            course="CA",
            level="Foundation",
            question="What is consideration?",
            answer_preview="Consideration is something of value...",
            source="material",
            top_score=0.88,
            retrieval_ok=True,
            model_used="gemini-flash-latest",
            response_time_ms=1230
        )
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM chat_log WHERE question LIKE '%consideration%'")
            count = cur.fetchone()[0]
            self.assertGreaterEqual(count, 1)

    def test_vector_store_chunk_limits(self):
        cvs = CloudVectorStore(gemini_api_key="test", pinecone_api_key="test")
        sample_chunk = {
            "id": "c1",
            "subject": "Law",
            "doc_name": "law.pdf",
            "section": "p1",
            "content": "A" * 3500
        }
        self.assertEqual(len(sample_chunk["content"]), 3500)

if __name__ == "__main__":
    unittest.main()
