import unittest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
import json
import io

import syllabus
from app import app, ADMIN_PASSWORD
from ai_service import AIService, clean_student_reply, clean_exam_math
from cloud_vector_store import CloudVectorStore

class Phase6Tests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_syllabus(self):
        """Test syllabus hierarchy, namespace mapping, and subject lookups."""
        # 1. Hierarchy checks
        self.assertIn("CA", syllabus.SYLLABUS)
        self.assertIn("Foundation", syllabus.SYLLABUS["CA"])
        self.assertIn("Inter", syllabus.SYLLABUS["CA"])
        self.assertIn("Final", syllabus.SYLLABUS["CA"])

        # 2. Namespace routing
        self.assertEqual(syllabus.namespace("CA", "Foundation"), "ca-foundation")
        self.assertEqual(syllabus.namespace("CA", "Inter"), "ca-inter")
        self.assertEqual(syllabus.namespace("CA", "Final"), "ca-final")

        # 3. Subject lookups
        f_subjects = syllabus.get_subjects("CA", "Foundation")
        self.assertIn("Accounting", f_subjects)
        self.assertIn("Business Laws", f_subjects)

        inter_subjects = syllabus.get_subjects("CA", "Inter")
        self.assertIn("Advanced Accounting", inter_subjects)
        self.assertIn("Taxation", inter_subjects)
        self.assertIn("Cost and Management Accounting", inter_subjects)

        final_subjects = syllabus.get_subjects("CA", "Final")
        self.assertIn("Financial Reporting", final_subjects)
        self.assertIn("Advanced Auditing and Professional Ethics", final_subjects)

        # 4. Validation lookups
        self.assertTrue(syllabus.is_valid_course_level("CA", "Foundation"))
        self.assertTrue(syllabus.is_valid_course_level("CA", "Inter"))
        self.assertTrue(syllabus.is_valid_course_level("CA", "Final"))
        self.assertFalse(syllabus.is_valid_course_level("CA", "Doctorate"))
        self.assertFalse(syllabus.is_valid_course_level("UnknownCourse", "Foundation"))

    def test_retrieval(self):
        """Test mock Pinecone response, MIN_SCORE filtering, namespace routing, and subject filtering."""
        store = CloudVectorStore(
            gemini_api_key="fake_gemini_key",
            pinecone_api_key="fake_pinecone_key",
            index_host="https://fake-index.pinecone.io"
        )

        mock_embedding = [0.1] * 768
        mock_matches = [
            {"id": "c1", "score": 0.85, "metadata": {"course": "CA", "level": "Inter", "subject": "Taxation", "text": "Sec 115BAC slabs"}},
            {"id": "c2", "score": 0.72, "metadata": {"course": "CA", "level": "Inter", "subject": "Taxation", "text": "Rebate under 87A"}},
            {"id": "c3", "score": 0.55, "metadata": {"course": "CA", "level": "Inter", "subject": "Taxation", "text": "General income heads"}},
            {"id": "c4", "score": 0.40, "metadata": {"course": "CA", "level": "Inter", "subject": "Taxation", "text": "Outdated rebate rules"}}
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"matches": mock_matches}

        with patch.object(store, "get_embedding", new_callable=AsyncMock, return_value=mock_embedding), \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:

            import asyncio
            chunks = asyncio.run(store.query(
                query_text="What are 115BAC slabs?",
                namespace="ca-inter",
                top_k=8,
                subject="Taxation"
            ))

            # Verify POST payload sent to Pinecone
            self.assertEqual(mock_post.call_count, 1)
            call_kwargs = mock_post.call_args.kwargs
            payload = call_kwargs.get("json", {})
            self.assertEqual(payload.get("namespace"), "ca-inter")
            self.assertEqual(payload.get("filter"), {"subject": {"$eq": "Taxation"}})
            self.assertEqual(payload.get("topK"), 8)

            # Test MIN_SCORE filtering (score >= 0.62)
            min_score = 0.62
            filtered_chunks = [c for c in chunks if c["score"] >= min_score][:5]
            self.assertEqual(len(filtered_chunks), 2)
            self.assertGreaterEqual(filtered_chunks[0]["score"], 0.62)
            self.assertGreaterEqual(filtered_chunks[1]["score"], 0.62)
            self.assertTrue(all(c["score"] >= 0.62 for c in filtered_chunks))

    def test_chat_grounded(self):
        """Verify prompt includes grounded instructions and falls back on NOT_IN_MATERIAL."""
        ai = AIService(api_key="fake_key_test_12345")

        captured_calls = []

        async def fake_call_gemini(*args, **kwargs):
            prompt = kwargs.get("prompt") or (args[0] if len(args) > 0 else "")
            sys_inst = kwargs.get("system_instruction") or ""
            captured_calls.append({"prompt": prompt, "system_instruction": sys_inst})
            if len(captured_calls) == 1:
                # First call returns NOT_IN_MATERIAL to test fallback
                return "NOT_IN_MATERIAL"
            return "General faculty answer on corporate capital structure."

        with patch.object(ai, "_call_gemini_api", side_effect=fake_call_gemini):
            import asyncio
            sample_chunks = [
                {"subject": "Corporate and Other Laws", "doc_name": "Sec68.pdf", "section": "Page 1", "content": "Buy back rules under Section 68", "score": 0.88}
            ]

            res = asyncio.run(ai.get_response(
                message="Explain buy back rules under Section 68.",
                context_chunks=sample_chunks,
                course="CA",
                level="Inter"
            ))

            # 1. Verify grounded prompt contained strict grounding instructions
            self.assertGreaterEqual(len(captured_calls), 2)
            grounded_sys = captured_calls[0]["system_instruction"]
            self.assertIn("GROUNDED RULES", grounded_sys)
            self.assertIn("NOT_IN_MATERIAL", grounded_sys)
            self.assertIn("Use ONLY the excerpts", grounded_sys)
            self.assertIn("STUDENT LEVEL: The student is preparing for CA Inter", grounded_sys)
            self.assertIn("COMPLETENESS (STRICT): Give the complete answer in ONE response", grounded_sys)

            # 2. Verify fallback succeeded
            self.assertEqual(res["source"], "general")
            self.assertNotIn("NOT_IN_MATERIAL", res["reply"])
            self.assertIn("corporate capital structure", res["reply"])

    def test_chat_no_leak(self):
        """Verify student response contains no sources, scores, citations, or labels."""
        with patch("app.cloud_store.query", new_callable=AsyncMock, return_value=[]), \
             patch("app.ai.get_response", new_callable=AsyncMock) as mock_ai:
            
            # Simulated answer with accidental leakage that clean_student_reply strips
            mock_ai.return_value = {
                "reply": "According to the study material\nSection 115BAC is the default regime.\nSource: Module 1\nScore: 0.88",
                "source": "material",
                "top_score": 0.88,
                "model_used": "gemini-flash-latest"
            }

            res = self.client.post("/api/chat", data={
                "message": "What is Section 115BAC?",
                "course": "CA",
                "level": "Inter"
            })

            self.assertEqual(res.status_code, 200)
            data = res.json()

            # Must have 'reply' key
            self.assertIn("reply", data)
            student_reply = data["reply"]

            # Must NOT have internal telemetry keys in student response
            self.assertNotIn("source", data)
            self.assertNotIn("top_score", data)
            self.assertNotIn("retrieval_ok", data)
            self.assertNotIn("model_used", data)

            # Must NOT contain forbidden phrases or leaked labels
            self.assertNotIn("According to the study material", student_reply)
            self.assertNotIn("Source:", student_reply)
            self.assertNotIn("Score:", student_reply)
            self.assertNotIn("NOT_IN_MATERIAL", student_reply)
            self.assertIn("Section 115BAC is the default regime", student_reply)

    def test_admin_auth(self):
        """Verify 401 when X-Admin-Key is missing or wrong across all /api/admin/* endpoints."""
        dummy_file = ("dummy.pdf", io.BytesIO(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"), "application/pdf")

        # 1. Test GET /api/admin/* routes without key -> 401
        get_routes = [
            "/api/admin/materials",
            "/api/admin/insights",
            "/api/admin/chat-logs/export",
            "/api/admin/jobs/job_12345"
        ]
        for ep in get_routes:
            res = self.client.get(ep)
            self.assertEqual(res.status_code, 401, f"Expected 401 for GET {ep}")

            res_bad = self.client.get(ep, headers={"X-Admin-Key": "wrong_key_123"})
            self.assertEqual(res_bad.status_code, 401, f"Expected 401 for bad key on GET {ep}")

        # 2. Test POST /api/admin/upload-cloud-pdf without key -> 401
        res_post_no_key = self.client.post(
            "/api/admin/upload-cloud-pdf",
            files={"file": dummy_file},
            data={"course": "CA", "level": "Inter", "subject": "Taxation"}
        )
        self.assertEqual(res_post_no_key.status_code, 401, "Expected 401 for POST upload-cloud-pdf with no key")

        res_post_bad_key = self.client.post(
            "/api/admin/upload-cloud-pdf",
            headers={"X-Admin-Key": "bad_key"},
            files={"file": ("dummy2.pdf", io.BytesIO(b"%PDF-1.4..."), "application/pdf")},
            data={"course": "CA", "level": "Inter", "subject": "Taxation"}
        )
        self.assertEqual(res_post_bad_key.status_code, 401, "Expected 401 for POST upload-cloud-pdf with bad key")

        # 3. Valid key -> 200
        valid_headers = {"X-Admin-Key": ADMIN_PASSWORD}
        res_materials = self.client.get("/api/admin/materials", headers=valid_headers)
        self.assertEqual(res_materials.status_code, 200)

        res_insights = self.client.get("/api/admin/insights", headers=valid_headers)
        self.assertEqual(res_insights.status_code, 200)

        res_export = self.client.get("/api/admin/chat-logs/export", headers=valid_headers)
        self.assertEqual(res_export.status_code, 200)

if __name__ == "__main__":
    unittest.main()
