import json
import unittest
from unittest.mock import patch

from app.agent import llm_provider


class FakeResponse:
    def __init__(self, body):
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.body


def completion(content):
    return {"choices": [{"message": {"content": content}}]}


class LlmProviderTests(unittest.TestCase):
    def configured(self):
        return patch.multiple(
            llm_provider,
            LLM_ENABLED=True,
            LLM_BASE_URL="https://compatible.example/v1",
            LLM_API_KEY="test-only-key",
            LLM_MODEL="compatible-model",
        )

    def test_requires_enabled_and_complete_configuration(self):
        with patch.multiple(
            llm_provider,
            LLM_ENABLED=False,
            LLM_BASE_URL="https://compatible.example/v1",
            LLM_API_KEY="test-only-key",
            LLM_MODEL="compatible-model",
        ):
            self.assertFalse(llm_provider.llm_is_configured())
        with patch.multiple(
            llm_provider,
            LLM_ENABLED=True,
            LLM_BASE_URL="https://compatible.example/v1",
            LLM_API_KEY="",
            LLM_MODEL="compatible-model",
        ):
            self.assertFalse(llm_provider.llm_is_configured())

    def test_successful_openai_compatible_response_is_schema_validated(self):
        body = completion(json.dumps({
            "target": "esr1",
            "num_samples": 5,
            "qed_threshold": None,
            "sa_threshold": 3.5,
            "qed_priority": True,
            "run_docking": True,
            "dock_top_k": 1,
        }))
        with self.configured(), patch.object(
            llm_provider.request, "urlopen", return_value=FakeResponse(body)
        ) as urlopen:
            plan = llm_provider.parse_with_llm("test prompt")
        self.assertEqual(plan.target, "ESR1")
        self.assertEqual(plan.num_samples, 5)
        self.assertEqual(plan.parser, "llm")
        self.assertEqual(urlopen.call_args.args[0].full_url, "https://compatible.example/v1/chat/completions")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 10.0)

    def test_full_chat_completions_url_is_not_duplicated(self):
        self.assertEqual(
            llm_provider.chat_completions_url("https://compatible.example/v1/chat/completions"),
            "https://compatible.example/v1/chat/completions",
        )

    def test_timeout_falls_back_without_external_retry(self):
        with self.configured(), patch.object(
            llm_provider.request, "urlopen", side_effect=TimeoutError("mock timeout")
        ) as urlopen:
            self.assertIsNone(llm_provider.try_parse_with_llm("ESR1 生成 3 个分子"))
        urlopen.assert_called_once()

    def test_malformed_json_falls_back(self):
        with self.configured(), patch.object(
            llm_provider.request,
            "urlopen",
            return_value=FakeResponse(completion("not-json")),
        ):
            self.assertIsNone(llm_provider.try_parse_with_llm("ESR1 生成 3 个分子"))

    def test_invalid_plan_falls_back_after_pydantic_validation(self):
        invalid = completion(json.dumps({
            "target": "ESR1",
            "num_samples": 99,
            "qed_threshold": None,
            "sa_threshold": None,
            "qed_priority": True,
            "run_docking": False,
            "dock_top_k": None,
        }))
        with self.configured(), patch.object(
            llm_provider.request, "urlopen", return_value=FakeResponse(invalid)
        ):
            self.assertIsNone(llm_provider.try_parse_with_llm("ESR1 生成很多分子"))


if __name__ == "__main__":
    unittest.main()
