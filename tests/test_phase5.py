import unittest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
import io
import csv
import db
from app import app, ADMIN_PASSWORD

class Phase5Tests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        db.init_db()

    def test_db_chat_insights_and_gaps(self):
        """Test logging interactions and computing course/level stats and gaps."""
        # Insert a material-grounded question
        db.log_chat_interaction(
            timestamp="2026-10-26T02:00:00",
            course="CA",
            level="Inter",
            question="Explain section 115BAC slabs.",
            answer_preview="Section 115BAC provides concessional tax rates...",
            source="material",
            top_score=0.88,
            retrieval_ok=True,
            model_used="gemini-flash-latest",
            response_time_ms=1200
        )

        # Insert a general knowledge question (below MIN_SCORE / gap in materials)
        db.log_chat_interaction(
            timestamp="2026-10-26T02:05:00",
            course="CA",
            level="Inter",
            question="What are the penalties for late filing under section 234F?",
            answer_preview="Late filing fee under section 234F is Rs 5,000...",
            source="general",
            top_score=0.42,
            retrieval_ok=True,
            model_used="gemini-flash-latest",
            response_time_ms=950
        )

        insights = db.get_chat_insights(limit=50)
        self.assertIn("total_chats", insights)
        self.assertIn("material_pct", insights)
        self.assertIn("general_pct", insights)
        self.assertIn("by_course_level", insights)
        self.assertIn("recent_chats", insights)
        self.assertIn("min_score_threshold", insights)
        self.assertEqual(insights["min_score_threshold"], 0.62)

        self.assertGreaterEqual(insights["total_chats"], 2)
        self.assertIn("CA", insights["by_course_level"])
        self.assertIn("Inter", insights["by_course_level"]["CA"])

        # Check that the low-score question is flagged as a gap
        logs = insights["recent_chats"]
        gap_logs = [l for l in logs if l.get("is_low_score")]
        self.assertTrue(any("234F" in l["question"] for l in gap_logs))

    def test_admin_insights_api_auth(self):
        """GET /api/admin/insights requires X-Admin-Key header."""
        # 1. No key -> 401
        res = self.client.get("/api/admin/insights")
        self.assertEqual(res.status_code, 401)

        # 2. Invalid key -> 401
        res = self.client.get("/api/admin/insights", headers={"X-Admin-Key": "wrong_key"})
        self.assertEqual(res.status_code, 401)

        # 3. Valid key -> 200
        res = self.client.get("/api/admin/insights", headers={"X-Admin-Key": ADMIN_PASSWORD})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("total_chats", data)
        self.assertIn("material_pct", data)
        self.assertIn("by_course_level", data)
        self.assertIn("recent_chats", data)

    def test_admin_chat_logs_csv_export(self):
        """GET /api/admin/chat-logs/export produces valid CSV with expected columns."""
        # 1. Without auth -> 401
        res = self.client.get("/api/admin/chat-logs/export")
        self.assertEqual(res.status_code, 401)

        # 2. With auth -> 200 and text/csv
        res = self.client.get("/api/admin/chat-logs/export", headers={"X-Admin-Key": ADMIN_PASSWORD})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("content-type"), "text/csv; charset=utf-8")
        self.assertIn("attachment; filename=excel_ai_chat_logs.csv", res.headers.get("content-disposition", ""))

        # Parse CSV content
        csv_file = io.StringIO(res.text)
        reader = csv.reader(csv_file)
        header = next(reader)
        expected_cols = [
            "timestamp", "course", "level", "question", "answer_preview",
            "source", "top_score", "model_used", "response_time_ms"
        ]
        self.assertEqual(header, expected_cols)

        # Ensure rows exist and are non-empty
        rows = list(reader)
        self.assertGreaterEqual(len(rows), 1)

if __name__ == "__main__":
    unittest.main()
