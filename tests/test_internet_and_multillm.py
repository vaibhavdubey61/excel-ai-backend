import unittest
from unittest.mock import patch, AsyncMock
from ai_service import AIService, perform_web_search, is_forced_internet_query

class TestInternetAndMultiLLM(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ai = AIService(api_key="fake_key_12345")

    def test_forced_internet_query_detection(self):
        self.assertTrue(is_forced_internet_query("Please search the internet for recent ICAI circulars."))
        self.assertTrue(is_forced_internet_query("Search web for latest notification"))
        self.assertTrue(is_forced_internet_query("What are the exam dates for May 2026?"))
        self.assertTrue(is_forced_internet_query("Look up online if there is any announcement"))
        self.assertFalse(is_forced_internet_query("Explain Section 115BAC slabs"))
        self.assertFalse(is_forced_internet_query("Calculate Material Cost Variance"))

    async def test_forced_internet_answering(self):
        mock_web_results = [
            {"title": "ICAI May 2026 Notification", "snippet": "Foundation exams start from May 15, 2026."}
        ]
        with patch("ai_service.perform_web_search", return_value=mock_web_results), \
             patch.object(self.ai, "_call_gemini_api", new_callable=AsyncMock, return_value="The ICAI May 2026 Foundation exams are scheduled to commence from May 15, 2026."):
            
            res = await self.ai.get_response(
                message="Search the internet for ICAI May 2026 exam schedule",
                course="CA",
                level="Foundation"
            )
            self.assertEqual(res["source"], "internet")
            self.assertIn("May 15, 2026", res["reply"])

    async def test_multi_llm_openai_routing(self):
        self.ai.openai_api_key = "sk-test-fake-openai-key"
        self.ai.preferred_llm = "openai"

        with patch.object(self.ai, "_call_openai_api", new_callable=AsyncMock, return_value="OpenAI faculty answer.") as mock_openai:
            reply = await self.ai._call_llm("Test prompt", system_instruction="Test system")
            self.assertEqual(reply, "OpenAI faculty answer.")
            self.assertEqual(mock_openai.call_count, 1)

if __name__ == "__main__":
    unittest.main()
