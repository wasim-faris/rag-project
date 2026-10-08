import os
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase
from rest_framework.test import APIClient

from rag.ai import (
    OpenRouterResponseError,
    RATE_LIMIT_MESSAGE,
    extract_final_answer,
    ask_ai,
)
from rag.views import ANSWER_CACHE


class ExtractAnswerTests(SimpleTestCase):
    def test_extracts_content_from_message_only(self):
        response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "reasoning": "Do not display this reasoning.",
                        "content": [
                            "The working hours are 9 AM to 6 PM, Monday to Friday."
                        ],
                        "user_safety": "safe",
                    }
                }
            ]
        }

        self.assertEqual(
            extract_final_answer(response),
            "The working hours are 9 AM to 6 PM, Monday to Friday.",
        )

    def test_content_wins_over_reasoning(self):
        response = {
            "choices": [
                {
                    "message": {
                        "reasoning": "This is private reasoning.",
                        "content": "Kannur, Kerala.",
                        "safety": {"status": "safe"},
                    }
                }
            ]
        }

        self.assertEqual(extract_final_answer(response), "Kannur, Kerala.")

    def test_returns_no_answer_when_content_missing(self):
        response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "safety": "safe",
                    }
                }
            ]
        }

        self.assertEqual(extract_final_answer(response), "")

    def test_does_not_fall_back_to_reasoning_when_content_is_empty(self):
        response = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": "   ",
                        "reasoning": "This must never be treated as the answer.",
                    },
                }
            ]
        }

        self.assertEqual(extract_final_answer(response), "")


class AskAiRateLimitTests(SimpleTestCase):
    def test_raises_for_embedded_openrouter_error_on_http_200(self):
        response = Mock(
            status_code=200,
            headers={},
            json=Mock(return_value={"error": {"message": "Reasoning is mandatory"}}),
            raise_for_status=Mock(),
        )

        with patch.dict(
            os.environ,
            {"OPENROUTER_API_KEY": "test-key", "OPENROUTER_MODEL": "openrouter/free"},
            clear=False,
        ), patch("rag.ai.get_session") as mock_get_session:
            session = Mock()
            session.post.return_value = response
            mock_get_session.return_value = session

            with self.assertRaisesRegex(OpenRouterResponseError, "Reasoning is mandatory") as raised:
                ask_ai("Where is the office located?")

        self.assertEqual(raised.exception.http_status, 200)
        self.assertTrue(raised.exception.content_empty)
        self.assertEqual(session.post.call_count, 1)

    def test_raises_clean_rate_limit_without_retry(self):
        class FakeResponse:
            status_code = 429
            headers = {}
            text = '{"error": {"message": "Too Many Requests"}}'
            json = Mock(return_value={"error": {"message": "Too Many Requests"}})

            def __init__(self):
                self.request = Mock(headers={"Authorization": "Bearer test-key"})

            def raise_for_status(self):
                raise requests.HTTPError("429 Too Many Requests", response=self)

        with patch.dict(
            os.environ,
            {"OPENROUTER_API_KEY": "test-key", "OPENROUTER_MODEL": "openrouter/free"},
            clear=False,
        ):
            with patch("rag.ai.get_session") as mock_get_session:
                mock_session = Mock()
                mock_session.post.return_value = FakeResponse()
                mock_get_session.return_value = mock_session

                with self.assertRaisesRegex(
                    RuntimeError,
                    "OpenRouter rate limit reached. Please wait before trying again.",
                ):
                    ask_ai("Question: What are the working hours?\n\nAnswer:")

                self.assertEqual(mock_session.post.call_count, 1)


class AskQuestionViewTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        ANSWER_CACHE.clear()

    def tearDown(self):
        ANSWER_CACHE.clear()

    @patch("rag.views.retrieve_context_with_score")
    @patch("rag.views.ask_ai")
    def test_one_api_request_makes_two_context_isolated_calls(self, mock_ask, mock_retrieval):
        context = "Office location: Kannur, Kerala."
        mock_retrieval.return_value = (context, 4)
        mock_ask.side_effect = ["General answer.", "Grounded answer."]

        response = self.client.post(
            "/api/ask/",
            {"question": "Where is the office located?"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_retrieval.call_count, 1)
        self.assertEqual(mock_ask.call_count, 2)
        without_prompt, with_prompt = [call.args[0] for call in mock_ask.call_args_list]
        self.assertIn("You are a concise FAQ assistant.", without_prompt)
        self.assertIn("Where is the office located?", without_prompt)
        self.assertIn("Final answer:", without_prompt)
        self.assertNotIn(context, without_prompt)
        self.assertIn(context, with_prompt)
        self.assertIn('"I don\'t have that information in my knowledge base."', with_prompt)
        self.assertEqual(response.data["without_context"], "General answer.")
        self.assertEqual(response.data["with_context"], "Grounded answer.")
        self.assertEqual(response.data["relevance_score"], 4)

    @patch("rag.views.retrieve_context_with_score")
    def test_one_api_request_sends_exactly_two_openrouter_posts(self, mock_retrieval):
        context = "Office location: Kannur, Kerala."
        mock_retrieval.return_value = (context, 4)
        session = Mock()
        session.post.side_effect = [
            Mock(
                status_code=200,
                headers={},
                raise_for_status=Mock(),
                json=Mock(return_value={"choices": [{"message": {"content": "General answer."}}]}),
            ),
            Mock(
                status_code=200,
                headers={},
                raise_for_status=Mock(),
                json=Mock(return_value={"choices": [{"message": {"content": "Grounded answer."}}]}),
            ),
        ]

        with patch.dict(
            os.environ,
            {"OPENROUTER_API_KEY": "test-key", "OPENROUTER_MODEL": "test-model"},
        ), patch("rag.ai.get_session", return_value=session):
            response = self.client.post(
                "/api/ask/",
                {"question": "Where is the office located?"},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(session.post.call_count, 2)
        without_payload, with_payload = [call.kwargs["json"] for call in session.post.call_args_list]
        without_prompt = without_payload["messages"][0]["content"]
        with_prompt = with_payload["messages"][0]["content"]
        self.assertIn("You are a concise FAQ assistant.", without_prompt)
        self.assertIn("Do not show your thinking process.", without_prompt)
        self.assertIn("Where is the office located?", without_prompt)
        self.assertNotIn(context, without_prompt)
        self.assertNotIn("Relevance score", without_prompt)
        self.assertIn(context, with_prompt)
        self.assertIn("Final answer:", without_prompt)
        self.assertIn("Final answer:", with_prompt)
        self.assertEqual(without_payload["max_tokens"], 1200)
        self.assertEqual(with_payload["max_tokens"], 1200)
        self.assertEqual(without_payload["reasoning"], {"exclude": True})
        self.assertEqual(with_payload["reasoning"], {"exclude": True})
        self.assertEqual(response.data["without_context"], "General answer.")
        self.assertEqual(response.data["with_context"], "Grounded answer.")

    @patch("rag.views.retrieve_context_with_score")
    @patch("rag.views.ask_ai", side_effect=RuntimeError(RATE_LIMIT_MESSAGE))
    def test_openrouter_429_is_returned_without_retry(self, mock_ask, mock_retrieval):
        mock_retrieval.return_value = ("Office location: Kannur, Kerala.", 4)

        response = self.client.post(
            "/api/ask/",
            {"question": "Where is the office located?"},
            format="json",
        )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["error"], RATE_LIMIT_MESSAGE)
        self.assertEqual(mock_ask.call_count, 1)

    @patch("rag.views.retrieve_context_with_score")
    @patch(
        "rag.views.ask_ai",
        side_effect=OpenRouterResponseError(
            "OpenRouter returned an empty final answer",
            http_status=200,
            model="test-model",
            finish_reason="stop",
            content_empty=True,
        ),
    )
    def test_empty_model_content_is_an_api_error_not_an_answer(self, mock_ask, mock_retrieval):
        mock_retrieval.return_value = ("Office location: Kannur, Kerala.", 4)

        response = self.client.post(
            "/api/ask/",
            {"question": "Where is the office located?"},
            format="json",
        )

        self.assertEqual(response.status_code, 502)
        self.assertNotIn("without_context", response.data)
        self.assertEqual(response.data["error"], "OpenRouter returned an empty final answer")
        self.assertEqual(response.data["http_status"], 200)
        self.assertEqual(response.data["model"], "test-model")
        self.assertEqual(response.data["finish_reason"], "stop")
        self.assertTrue(response.data["content_empty"])
        self.assertEqual(mock_ask.call_count, 1)
