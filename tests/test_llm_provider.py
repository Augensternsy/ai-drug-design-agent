import io
import json
import unittest
from urllib import error
from unittest.mock import patch

from app.agent import llm_provider
from app.agent.service import AgentService
from app.schemas.api_models import AgentGenerateRequest


class FakeResponse:
    def __init__(self, body):
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.body

    @property
    def status(self):
        return 200


def completion(content):
    return {"choices": [{"message": {"content": content}}]}


class LlmProviderTests(unittest.TestCase):
    def configured(self):
        return patch.multiple(
            llm_provider,
            LLM_ENABLED=True,
            LLM_BASE_URL="https://api.qnaigc.com/v1",
            LLM_API_KEY="test-only-key",
            LLM_MODEL="deepseek-v4-flash",
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
            self.assertIsNone(
                llm_provider.try_parse_with_llm("针对 ESR1 生成 1 个候选分子")
            )

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
            prompt = "帮我针对 ESR1 生成 1 个候选分子，不进行 Vina 对接。"
            plan = llm_provider.parse_with_llm(prompt)
        self.assertEqual(plan.target, "ESR1")
        self.assertEqual(plan.num_samples, 5)
        self.assertEqual(plan.parser, "llm")
        outgoing_request = urlopen.call_args.args[0]
        self.assertEqual(
            outgoing_request.full_url,
            "https://api.qnaigc.com/v1/chat/completions",
        )
        self.assertEqual(
            outgoing_request.get_header("Authorization"),
            "Bearer test-only-key",
        )
        request_json = json.loads(outgoing_request.data.decode("utf-8"))
        self.assertEqual(request_json["model"], "deepseek-v4-flash")
        self.assertEqual(request_json["messages"][1]["content"], prompt)
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 10.0)

    def test_http_error_logs_status_without_exposing_key(self):
        response = io.BytesIO(
            json.dumps({
                "error": {
                    "code": "model_not_found",
                    "type": "invalid_request_error",
                    "message": "Unknown model",
                }
            }).encode("utf-8")
        )
        http_error = error.HTTPError(
            "https://api.qnaigc.com/v1/chat/completions",
            400,
            "Bad Request",
            {},
            response,
        )
        with self.configured(), patch.object(
            llm_provider.request, "urlopen", side_effect=http_error
        ), self.assertLogs(llm_provider.logger, level="WARNING") as captured:
            self.assertIsNone(llm_provider.try_parse_with_llm("ESR1 生成 1 个分子"))
        logs = " ".join(captured.output)
        self.assertIn("http_status=400", logs)
        self.assertIn("error_code=model_not_found", logs)
        self.assertNotIn("test-only-key", logs)

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

    def test_llm_failure_uses_rules_with_chinese_semantics(self):
        prompt = "帮我针对 ESR1 生成 1 个候选分子，QED 优先，不进行 Vina 对接。"
        with self.configured(), patch.object(
            llm_provider.request, "urlopen", side_effect=TimeoutError("mock timeout")
        ):
            plan = AgentService.build_plan(AgentGenerateRequest(prompt=prompt))
        self.assertEqual(plan.parser, "rules")
        self.assertEqual(plan.num_samples, 1)
        self.assertFalse(plan.run_docking)

    def test_configuration_log_reports_presence_not_key(self):
        with self.configured(), patch.object(
            llm_provider.request, "urlopen", side_effect=TimeoutError("mock timeout")
        ), self.assertLogs(llm_provider.logger, level="INFO") as captured:
            llm_provider.try_parse_with_llm("ESR1 生成 1 个分子")
        logs = " ".join(captured.output)
        self.assertIn("LLM_API_KEY_PRESENT=true", logs)
        self.assertNotIn("test-only-key", logs)

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
