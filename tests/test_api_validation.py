import unittest

from fastapi.testclient import TestClient

from app.main import app, submission_cooldown


class ApiValidationTests(unittest.TestCase):
    def setUp(self):
        submission_cooldown.clear()
        self.client = TestClient(app)

    def test_unknown_target_returns_clear_400(self):
        response = self.client.post(
            "/api/generate",
            json={"target": "UNKNOWN", "num_samples": 1, "run_docking": False},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported target", response.json()["detail"])

    def test_sample_limit_returns_422_without_starting_task(self):
        response = self.client.post(
            "/api/generate",
            json={"target": "ESR1", "num_samples": 6, "run_docking": False},
        )
        self.assertEqual(response.status_code, 422)

    def test_agent_requires_verified_target(self):
        response = self.client.post(
            "/api/agent/generate",
            json={"prompt": "请生成 3 个候选分子"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("已验证靶点", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
