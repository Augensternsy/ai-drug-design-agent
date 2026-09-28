"""
Unit tests for evaluation API endpoints and backend integrity.
"""
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from app.main import app


class TestEvaluationAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_get_evaluation_report_success(self):
        response = self.client.get("/api/evaluation/report")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("intent_accuracy", data)
        self.assertIn("parameter_accuracy", data)
        self.assertIn("tool_calling_success", data)
        self.assertIn("task_success_rate", data)
        self.assertIn("total_cases", data)
        self.assertIn("summary", data)

        # Check values match evaluation results
        self.assertEqual(data["intent_accuracy"], 100.0)
        self.assertEqual(data["parameter_accuracy"], 100.0)
        self.assertEqual(data["tool_calling_success"], 100.0)
        self.assertEqual(data["task_success_rate"], 100.0)
        self.assertEqual(data["total_cases"], 156)

    def test_health_endpoint(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")

    def test_get_targets_endpoint(self):
        response = self.client.get("/api/targets")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("targets", data)
        self.assertGreater(len(data["targets"]), 0)


if __name__ == "__main__":
    unittest.main()
