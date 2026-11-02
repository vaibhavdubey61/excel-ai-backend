import unittest
from unittest.mock import patch, AsyncMock
import time
import os
import pybreaker

from ai_service import (
    AIService,
    llm_circuit_breaker,
    FALLBACK_DEMAND_MESSAGE,
    is_retryable_llm_error,
)


class TestCircuitBreakerAndRetry(unittest.IsolatedAsyncioTestCase):
    """Unit tests for Tenacity Exponential Backoff and Pybreaker Circuit Breaker."""

    def setUp(self):
        # Reset circuit breaker before each test
        llm_circuit_breaker.close()
        # Fast retry timeouts for quick test execution
        os.environ["RETRY_MIN_WAIT"] = "0.01"
        os.environ["RETRY_MAX_WAIT"] = "0.05"
        os.environ["RETRY_MULTIPLIER"] = "0.01"

    def tearDown(self):
        llm_circuit_breaker.close()

    def test_client_error_not_retried(self):
        """Do not retry on client errors (like 400 Bad Request), only on server errors or timeouts."""
        client_err = RuntimeError("Model gemini-1.5-flash returned HTTP 400: Bad Request - invalid argument")
        self.assertFalse(is_retryable_llm_error(client_err))

        server_err = RuntimeError("Model gemini-1.5-flash returned HTTP 503: Service Unavailable")
        self.assertTrue(is_retryable_llm_error(server_err))

        api_key_err = RuntimeError("Model gemini-1.5-flash returned HTTP 400: API_KEY_INVALID")
        self.assertTrue(is_retryable_llm_error(api_key_err))

    async def test_acceptance_criteria_invalid_key_retries_and_trips_breaker(self):
        """
        Acceptance Criteria: If I temporarily set an invalid API key, the system retries 3 times
        with increasing delays, then trips the circuit breaker and returns the fallback message
        instantly on the 4th attempt.
        """
        ai = AIService(api_key="AIzaSyInvalidKeyForTesting12345")
        llm_call_count = 0

        async def mock_gemini_failure(*args, **kwargs):
            nonlocal llm_call_count
            llm_call_count += 1
            raise RuntimeError("Model gemini-1.5-flash returned HTTP 400: API_KEY_INVALID")

        with patch.object(ai, "_call_gemini_api", side_effect=mock_gemini_failure):
            # Attempt 1 (first user request): retries up to 3 times
            res1 = await ai.get_response(
                message="What is Section 115BAC?",
                course="CA",
                level="Inter"
            )

            # System must have retried 3 times
            self.assertEqual(llm_call_count, 3)
            # Circuit breaker must now be tripped to OPEN
            self.assertEqual(llm_circuit_breaker.current_state, "open")
            # Must return the user-friendly fallback response
            self.assertEqual(res1["reply"], FALLBACK_DEMAND_MESSAGE)
            self.assertEqual(res1["source"], "circuit_breaker")

            # 4th attempt (next user request): must fail fast instantly without calling LLM again
            t0 = time.time()
            res2 = await ai.get_response(
                message="Tell me more about tax slabs",
                course="CA",
                level="Inter"
            )
            elapsed = time.time() - t0

            # Instant return (< 0.05 seconds)
            self.assertLess(elapsed, 0.05)
            # LLM was NOT called again (call count remains 3)
            self.assertEqual(llm_call_count, 3)
            # Circuit breaker remains OPEN
            self.assertEqual(llm_circuit_breaker.current_state, "open")
            # Returns the fallback message
            self.assertEqual(res2["reply"], FALLBACK_DEMAND_MESSAGE)

    async def test_streaming_fails_fast_when_circuit_open(self):
        """When circuit breaker is open, stream_response yields fallback message immediately."""
        llm_circuit_breaker.open()
        ai = AIService(api_key="AIzaSyValidKeyForTesting12345")

        tokens = []
        async for token in ai.stream_response(
            message="Explain depreciation",
            course="CA",
            level="Inter"
        ):
            tokens.append(token)

        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0], FALLBACK_DEMAND_MESSAGE)


if __name__ == "__main__":
    unittest.main()
