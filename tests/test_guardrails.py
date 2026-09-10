import unittest

from pydantic import ValidationError

from app.schemas.api_models import GenerateRequest
from app.services.rate_limit_service import SubmissionCooldown


class GuardrailTests(unittest.TestCase):
    def test_generate_request_rejects_more_than_five(self):
        with self.assertRaises(ValidationError):
            GenerateRequest(target="ESR1", num_samples=6)

    def test_generate_request_validates_property_thresholds(self):
        with self.assertRaises(ValidationError):
            GenerateRequest(target="ESR1", num_samples=1, qed_threshold=1.2)
        with self.assertRaises(ValidationError):
            GenerateRequest(target="ESR1", num_samples=1, sa_threshold=0.5)

    def test_submission_cooldown_returns_retry_seconds(self):
        limiter = SubmissionCooldown(15)
        self.assertEqual(limiter.check("client", now=100), 0)
        self.assertEqual(limiter.check("client", now=105), 10)
        self.assertEqual(limiter.check("client", now=116), 0)


if __name__ == "__main__":
    unittest.main()
