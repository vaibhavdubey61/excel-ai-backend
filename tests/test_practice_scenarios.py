import unittest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
import json

from app import app
from ai_service import AIService, detect_interaction_scenario

class TestPracticeScenarios(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ai = AIService(api_key="fake_key_test_12345")
        self.client = TestClient(app)

    def test_detect_interaction_scenario(self):
        """Test accurate scenario classification across all student queries."""
        # 1. Practice & Questions
        self.assertEqual(detect_interaction_scenario("I want to practice"), "PRACTICE")
        self.assertEqual(detect_interaction_scenario("Give me questions from Standard Costing"), "PRACTICE")
        self.assertEqual(detect_interaction_scenario("Quiz me on SA 500"), "PRACTICE")
        self.assertEqual(detect_interaction_scenario("Can you give me 3 questions on buyback?"), "PRACTICE")
        self.assertEqual(detect_interaction_scenario("Give me some practice problems on variances"), "PRACTICE")

        # 2. Answer-Writing Practice
        self.assertEqual(detect_interaction_scenario("Give me question for answer writing for corporate law"), "ANSWER_WRITING")
        self.assertEqual(detect_interaction_scenario("I want to practice answer writing for taxation"), "ANSWER_WRITING")
        self.assertEqual(detect_interaction_scenario("Give me a case study question to practice writing"), "ANSWER_WRITING")
        self.assertEqual(detect_interaction_scenario("Give me a descriptive question on Section 135 CSR"), "ANSWER_WRITING")

        # 3. Explicit Solution Request
        self.assertEqual(detect_interaction_scenario("Give me the answer"), "SOLUTION_REQUEST")
        self.assertEqual(detect_interaction_scenario("What is the answer?"), "SOLUTION_REQUEST")
        self.assertEqual(detect_interaction_scenario("Show solution"), "SOLUTION_REQUEST")
        self.assertEqual(detect_interaction_scenario("What's the solution to this question?"), "SOLUTION_REQUEST")
        self.assertEqual(detect_interaction_scenario("Tell me the answer please"), "SOLUTION_REQUEST")
        self.assertEqual(detect_interaction_scenario("I give up, reveal answer"), "SOLUTION_REQUEST")
        self.assertEqual(detect_interaction_scenario("I don't know the answer"), "SOLUTION_REQUEST")

        # 4. Hint Request
        self.assertEqual(detect_interaction_scenario("Can I get a hint?"), "HINT_REQUEST")
        self.assertEqual(detect_interaction_scenario("Give me a hint"), "HINT_REQUEST")

        # 5. Student Submission
        self.assertEqual(detect_interaction_scenario("Here is my answer: Section 68 allows up to 25%"), "STUDENT_SUBMISSION")
        self.assertEqual(detect_interaction_scenario("1-A, 2-B, 3-C, 4-D"), "STUDENT_SUBMISSION")
        self.assertEqual(detect_interaction_scenario("My attempt: Net profit exceeds 5 crore so CSR is required"), "STUDENT_SUBMISSION")
        self.assertEqual(detect_interaction_scenario("What is the law?", has_image=True), "STUDENT_SUBMISSION")

        # Multi-turn submission: Coach asked practice question on last turn
        coach_history = [
            {"role": "assistant", "text": "**Question [5 Marks]**: ABC Ltd proposes buyback. Your turn: Draft your answer!"}
        ]
        self.assertEqual(detect_interaction_scenario("ABC Ltd can buy back shares up to 25% of paid up capital", history=coach_history), "STUDENT_SUBMISSION")

        # 6. General Conversation
        self.assertEqual(detect_interaction_scenario("Hi Coach"), "GENERAL_CONVERSATION")
        self.assertEqual(detect_interaction_scenario("I am feeling stressed about CA Inter exams"), "GENERAL_CONVERSATION")

        # 7. Concept Doubt
        self.assertEqual(detect_interaction_scenario("What are the conditions for buyback under Section 68?"), "CONCEPT_DOUBT")
        self.assertEqual(detect_interaction_scenario("Explain Section 115BAC slabs"), "CONCEPT_DOUBT")

    async def test_practice_request_withholds_answers(self):
        """Verify that practice question requests instruct AI to withhold solutions and follow up naturally."""
        captured_kwargs = {}

        async def mock_call_llm(prompt, **kwargs):
            captured_kwargs.update(kwargs)
            return (
                "Here are 2 practical questions for Cost & Management Accounting:\n\n"
                "**Question 1 [5 Marks]:** XYZ Ltd has standard quantity of 1000 units @ ₹10/unit. Actual quantity is 950 units @ ₹11/unit. Compute variances.\n\n"
                "Give it a shot! Drop your numbers or steps here, and I'll review your working notes. Or if you want me to reveal the full solution, just say the word!"
            )

        with patch.object(self.ai, "_call_llm", side_effect=mock_call_llm):
            res = await self.ai.get_response(
                message="Give me questions from Standard Costing",
                course="CA",
                level="Inter"
            )

            # Assertions on prompt instructions passed to LLM
            sys_inst = captured_kwargs.get("system_instruction", "")
            self.assertIn("TOPIC / SUBJECT PRACTICE REQUEST", sys_inst)
            self.assertIn("STRICTLY DO NOT REVEAL THE ANSWERS", sys_inst)
            self.assertIn("TALK LIKE A FRIEND", sys_inst)

            # Assertions on the response
            self.assertIn("Question 1", res["reply"])
            self.assertIn("Give it a shot!", res["reply"])
            # Ensure no leaked answers in student reply
            self.assertNotIn("Material Cost Variance =", res["reply"])

    async def test_answer_writing_request_withholds_answers(self):
        """Verify that answer-writing requests provide realistic exam question, time, marks, and withhold solutions."""
        captured_kwargs = {}

        async def mock_call_llm(prompt, **kwargs):
            captured_kwargs.update(kwargs)
            return (
                "Great choice! Let's practice answer writing for Corporate Law.\n\n"
                "**Question [5 Marks] | Recommended Time: 8-10 Minutes**\n"
                "ABC Ltd. has a net profit of ₹6 Crores during the preceding financial year. The Board decides not to constitute a CSR Committee stating that it has only 3 directors. Advise the company referring to provisions of Section 135.\n\n"
                "👉 **Your Turn:** Take about 8-10 minutes to draft your answer! Outline your statutory provisions, analysis, and conclusion right here. I'll evaluate it with step-wise marks! Or if you want to skip straight to the model answer, just let me know."
            )

        with patch.object(self.ai, "_call_llm", side_effect=mock_call_llm):
            res = await self.ai.get_response(
                message="Give me question for answer writing for corporate law",
                course="CA",
                level="Inter"
            )

            sys_inst = captured_kwargs.get("system_instruction", "")
            self.assertIn("ANSWER-WRITING PRACTICE REQUEST", sys_inst)
            self.assertIn("STRICTLY DO NOT PROVIDE THE ANSWER, HINTS, OR MODEL SOLUTION", sys_inst)
            self.assertIn("TALK LIKE A FRIEND", sys_inst)

            self.assertIn("Question", res["reply"])
            self.assertIn("5 Marks", res["reply"])
            self.assertIn("Your Turn", res["reply"])
            self.assertNotIn("Applicable Statutory Provisions:", res["reply"])

    async def test_solution_request_provides_complete_answer(self):
        """Verify that when a student explicitly asks for the answer, the full model solution is delivered."""
        captured_kwargs = {}

        async def mock_call_llm(prompt, **kwargs):
            captured_kwargs.update(kwargs)
            return (
                "Here is the complete ICAI model answer and how to present it:\n\n"
                "**Applicable Statutory Provisions:**\n"
                "As per Section 135(1) of the Companies Act, 2013, every company having a net profit of ₹5 crore or more during the immediately preceding financial year must constitute a CSR Committee.\n\n"
                "**Analysis & Application:**\n"
                "Since ABC Ltd.'s net profit is ₹6 Crore (exceeding ₹5 Crore), Section 135 applies.\n\n"
                "**Conclusion:**\n"
                "The contention of the Board is invalid. ABC Ltd. is statutorily required to constitute a CSR Committee."
            )

        with patch.object(self.ai, "_call_llm", side_effect=mock_call_llm):
            res = await self.ai.get_response(
                message="Give me the answer",
                course="CA",
                level="Inter",
                history=[
                    {"role": "user", "text": "Give me question for answer writing for corporate law"},
                    {"role": "assistant", "text": "Question [5 Marks]: ABC Ltd net profit ₹6 Crore..."}
                ]
            )

            sys_inst = captured_kwargs.get("system_instruction", "")
            self.assertIn("STUDENT ASKS FOR THE ANSWER / SOLUTION", sys_inst)
            self.assertIn("Applicable Statutory Provisions", res["reply"])
            self.assertIn("Section 135", res["reply"])
            self.assertIn("Conclusion", res["reply"])

    def test_api_chat_practice_and_solution_flow(self):
        """Test end-to-end /api/chat endpoint with practice question followed by answer request."""
        mock_practice_reply = (
            "Here is a great question to test your Corporate Law knowledge:\n\n"
            "**Question [5 Marks] | Recommended Time: 10 mins:**\n"
            "Explain the conditions for buyback under Section 68.\n\n"
            "Give it a try! Write your answer points right here. Or if you want the model answer right away, tell me!"
        )
        mock_solution_reply = (
            "Here is the full ICAI suggested answer:\n\n"
            "**Applicable Statutory Provisions: Section 68**\n"
            "1. Articles authorization\n2. Special Resolution\n3. Cap: 25% of paid-up capital and free reserves\n\n"
            "**Conclusion:** The company must comply with all statutory conditions."
        )

        with patch("app.cloud_store.query", new_callable=AsyncMock, return_value=[]), \
             patch("app.ai.get_response", new_callable=AsyncMock) as mock_get_resp:

            # Turn 1: Practice Request
            mock_get_resp.return_value = {
                "reply": mock_practice_reply,
                "source": "general",
                "top_score": 0.0,
                "model_used": "gemini-flash-latest"
            }

            resp1 = self.client.post("/api/chat", data={
                "message": "Give me question for answer writing for corporate law",
                "course": "CA",
                "level": "Inter"
            })
            self.assertEqual(resp1.status_code, 200)
            data1 = resp1.json()
            self.assertIn("reply", data1)
            self.assertIn("Question [5 Marks]", data1["reply"])
            self.assertIn("Give it a try!", data1["reply"])

            # Turn 2: Solution Request
            mock_get_resp.return_value = {
                "reply": mock_solution_reply,
                "source": "general",
                "top_score": 0.0,
                "model_used": "gemini-flash-latest"
            }

            history = [
                {"role": "user", "text": "Give me question for answer writing for corporate law"},
                {"role": "assistant", "text": mock_practice_reply}
            ]

            resp2 = self.client.post("/api/chat", data={
                "message": "Give me the answer",
                "course": "CA",
                "level": "Inter",
                "history": json.dumps(history)
            })
            self.assertEqual(resp2.status_code, 200)
            data2 = resp2.json()
            self.assertIn("reply", data2)
            self.assertIn("Section 68", data2["reply"])
            self.assertIn("Conclusion", data2["reply"])

if __name__ == "__main__":
    unittest.main()
