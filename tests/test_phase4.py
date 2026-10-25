import unittest
from unittest.mock import patch, AsyncMock
import json
from pydantic import ValidationError

from app import app
from ai_service import AIService, MCQQuestion, clean_exam_math
from fastapi.testclient import TestClient


class TestPhase4MCQ(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.ai = AIService(api_key="valid_test_api_key_12345")

    def test_clean_exam_math(self):
        # Test converting raw LaTeX formula to clean readable commerce format
        raw = r"Formula: ($\text{SP} \times [\text{SQ} - \text{AQ}])$ where $\text{SP} = ₹50$"
        cleaned = clean_exam_math(raw)
        self.assertNotIn(r"\text", cleaned)
        self.assertNotIn(r"\times", cleaned)
        self.assertNotIn("$", cleaned)
        self.assertIn("SP", cleaned)
        self.assertIn("×", cleaned)
        self.assertIn("[SQ - AQ]", cleaned)

        # Test fraction and spacing
        raw_frac = r"$\frac{\text{Net Profit}}{\text{Capital Employed}} \times 100$"
        cleaned_frac = clean_exam_math(raw_frac)
        self.assertNotIn(r"\frac", cleaned_frac)
        self.assertIn("(Net Profit / Capital Employed)", cleaned_frac)

    def test_mcq_question_pydantic_schema(self):
        # Valid question
        data = {
            "question": r"What is LRV when $\text{SR} = ₹10$, $\text{AR} = ₹12$, and $\text{AH} = 100$?",
            "options": {
                "A": r"₹200 (F)",
                "B": r"₹200 (A)",
                "C": r"₹100 (F)",
                "D": r"₹100 (A)"
            },
            "correct_answer": "B",
            "explanation": r"LRV = $\text{AH} \times (\text{SR} - \text{AR}) = 100 \times (10 - 12) = -200$ (Adverse)."
        }
        q = MCQQuestion(**data)
        self.assertEqual(q.correct_answer, "B")
        self.assertEqual(q.correct_option, "B")
        self.assertNotIn(r"\text", q.question)
        self.assertNotIn(r"\times", q.explanation)

        # Invalid correct_answer
        invalid_data = dict(data)
        invalid_data["correct_answer"] = "Z"
        with self.assertRaises(ValidationError):
            MCQQuestion(**invalid_data)

        # Missing option
        invalid_opts = dict(data)
        invalid_opts["options"] = {"A": "1", "B": "2"}
        with self.assertRaises(ValidationError):
            MCQQuestion(**invalid_opts)

    def test_endpoint_course_level_validation(self):
        # Invalid course/level returns 400
        resp = self.client.post("/api/mcq/generate", json={
            "course": "INVALID_COURSE",
            "level": "RandomLevel",
            "count": 5
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid course/level", resp.json()["detail"])

        # Valid course/level with mock AI service returns 200
        mock_response = {
            "topic": "Taxation",
            "subject": "Taxation",
            "course": "CA",
            "level": "Inter",
            "total_questions": 1,
            "questions": [
                {
                    "id": 1,
                    "question": "What is the basic exemption limit under Sec 115BAC?",
                    "options": {"A": "₹2,50,000", "B": "₹3,00,000", "C": "₹5,00,000", "D": "Nil"},
                    "correct_answer": "B",
                    "correct_option": "B",
                    "explanation": "Under Sec 115BAC, the basic exemption limit is ₹3,00,000."
                }
            ],
            "source": "general"
        }
        with patch("app.ai.generate_interactive_mcqs", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = mock_response
            resp = self.client.post("/api/mcq/generate", json={
                "course": "CA",
                "level": "Inter",
                "subject": "Taxation",
                "count": 5
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(len(data["questions"]), 1)
            self.assertEqual(data["questions"][0]["correct_answer"], "B")

    def test_endpoint_legacy_level_format(self):
        # Support legacy "CA_Inter" in level field
        mock_response = {
            "topic": "Random",
            "subject": "All Subjects",
            "course": "CA",
            "level": "Inter",
            "total_questions": 1,
            "questions": [
                {
                    "id": 1,
                    "question": "Sample Question",
                    "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                    "correct_answer": "A",
                    "correct_option": "A",
                    "explanation": "Sample Explanation"
                }
            ],
            "source": "general"
        }
        with patch("app.ai.generate_interactive_mcqs", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = mock_response
            resp = self.client.post("/api/mcq/generate", json={
                "level": "CA_Inter",
                "count": 10
            })
            self.assertEqual(resp.status_code, 200)

    @patch.object(AIService, "_call_gemini_api", new_callable=AsyncMock)
    async def test_mcq_retry_on_malformed_json(self, mock_gemini):
        # First call returns malformed JSON, second call returns valid JSON
        malformed = "THIS IS NOT VALID JSON"
        valid = json.dumps({
            "questions": [
                {
                    "id": 1,
                    "question": "Buyback section under Companies Act 2013?",
                    "options": {"A": "Sec 62", "B": "Sec 68", "C": "Sec 135", "D": "Sec 186"},
                    "correct_answer": "B",
                    "explanation": "Section 68 governs buyback of securities."
                }
            ]
        })
        mock_gemini.side_effect = [malformed, valid]

        result = await self.ai.generate_interactive_mcqs(
            course="CA",
            level="Inter",
            subject="Corporate and Other Laws",
            count=1
        )
        self.assertEqual(mock_gemini.call_count, 2)
        self.assertEqual(len(result["questions"]), 1)
        self.assertEqual(result["questions"][0]["correct_answer"], "B")

    @patch("app.cloud_store.query", new_callable=AsyncMock)
    @patch("app.ai.generate_interactive_mcqs", new_callable=AsyncMock)
    def test_mcq_pinecone_namespace_and_filter(self, mock_ai_mcq, mock_pinecone):
        mock_pinecone.return_value = [
            {"subject": "Taxation", "content": "Sec 115BAC text", "score": 0.85}
        ]
        mock_ai_mcq.return_value = {
            "questions": [],
            "source": "material"
        }
        resp = self.client.post("/api/mcq/generate", json={
            "course": "CA",
            "level": "Inter",
            "subject": "Taxation",
            "topic": "Section 115BAC",
            "count": 5
        })
        self.assertEqual(resp.status_code, 200)
        mock_pinecone.assert_called_once()
        _, kwargs = mock_pinecone.call_args
        self.assertEqual(kwargs.get("namespace"), "ca-inter")
        self.assertEqual(kwargs.get("subject"), "Taxation")
        mock_ai_mcq.assert_called_once()
        _, ai_kwargs = mock_ai_mcq.call_args
        self.assertEqual(ai_kwargs.get("course"), "CA")
        self.assertEqual(ai_kwargs.get("level"), "Inter")
        self.assertEqual(len(ai_kwargs.get("chunks")), 1)


if __name__ == "__main__":
    unittest.main()
