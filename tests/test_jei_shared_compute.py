import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from tools.jei_shared_compute import compute, execute


class SharedComputeTests(unittest.TestCase):
    def test_computes_real_observed_aggregates_without_oos_claim(self):
        result = compute({"groups": {"attack": {"3": {
            "completed": 62, "win_rate_pct": 25.81, "avg_estimated_net_pct": -3.778}}}})
        self.assertEqual(result["eligible_rows"], 1)
        self.assertTrue(result["observed_rows"][0]["underperforming"])
        self.assertEqual(result["independent_oos_trades"], 0)
        self.assertFalse(result["strategy_improvement_verified"])

    def test_both_providers_same_core_calculation(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "input.json"
            src.write_text(json.dumps({"groups": {"attack": {"3": {
                "completed": 30, "win_rate_pct": 60, "avg_estimated_net_pct": 1.5}}}}))
            a = json.loads(execute(src, Path(tmp) / "a", "google_colab", "sha").read_text())
            b = json.loads(execute(src, Path(tmp) / "b", "github_actions", "sha").read_text())
            self.assertEqual(a["observed_rows"], b["observed_rows"])
            self.assertEqual(a["source_sha256"], hashlib.sha256(src.read_bytes()).hexdigest())

    def test_missing_data_blocks(self):
        with self.assertRaises(ValueError):
            compute({"groups": {}})


if __name__ == "__main__":
    unittest.main()
