import unittest
from tools.jei_compute_provenance import make_record


class ProvenanceTests(unittest.TestCase):
    def test_actions_not_mislabeled_colab(self):
        result = make_record({"GITHUB_RUN_ID": "123", "GITHUB_SHA": "abc"}, {
            "status": "REPORTED", "short_horizon_risk": {"assessment": "REVIEW_WEAK_SIGNALS"}})
        self.assertEqual(result["compute_provider"], "github_actions")
        self.assertFalse(result["google_colab_runtime_verified"])
        self.assertFalse(result["google_colab_helpfulness_verified"])
        self.assertEqual(result["github_run_id"], "123")
        self.assertFalse(result["independent_oos_verified"])

    def test_missing_quality_not_reported_as_success(self):
        result = make_record({}, {"status": "BLOCKED"})
        self.assertEqual(result["quality_status"], "BLOCKED")
        self.assertFalse(result["meaningful_new_strategy_improvement_verified"])


if __name__ == "__main__":
    unittest.main()
