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

    def test_completed_longer_windows_are_included(self):
        observation = {"completed": 32, "win_rate_pct": 60, "avg_estimated_net_pct": 1}
        rows = compute({"groups": {"attack": {
            "20": observation, "40": observation, "60": observation,
            "30": {"completed": 0}}}})["observed_rows"]
        self.assertEqual([row["horizon_days"] for row in rows], [20, 40, 60])

    def test_invalid_observations_cannot_count_as_eligible(self):
        valid = {"completed": 31, "win_rate_pct": 55, "avg_estimated_net_pct": 2}
        for field, value in (
            ("win_rate_pct", 101), ("win_rate_pct", -1), ("win_rate_pct", float("nan")),
            ("avg_estimated_net_pct", float("inf")), ("avg_estimated_net_pct", -100.1),
        ):
            with self.subTest(field=field, value=value):
                report = compute({"groups": {"attack": {"3": valid, "7": {**valid, field: value}}}})
                self.assertEqual(report["eligible_rows"], 1)
                self.assertEqual([row["horizon_days"] for row in report["observed_rows"]], [3])

    def test_missing_data_blocks(self):
        with self.assertRaises(ValueError):
            compute({"groups": {}})


if __name__ == "__main__":
    unittest.main()
