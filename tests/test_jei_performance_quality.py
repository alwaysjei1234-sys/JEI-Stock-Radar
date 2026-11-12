import unittest
from tools.jei_performance_quality import inspect

class QualityTests(unittest.TestCase):
    def test_underperforming(self):
        report = {"groups": {"attack": {"3": {"completed": 62, "win_rate_pct": 25.81, "avg_estimated_net_pct": -3.778}}}}
        self.assertEqual(inspect(report)["groups"]["attack"]["3"]["state"], "UNDERPERFORMING")

    def test_insufficient_sample(self):
        report = {"groups": {"attack": {"15": {"completed": 15, "win_rate_pct": 80.0}}}}
        self.assertEqual(inspect(report)["groups"]["attack"]["15"]["state"], "INSUFFICIENT_EVIDENCE")

    def test_missing_data(self):
        self.assertEqual(inspect({})["status"], "BLOCKED")

    def test_no_false_oos_claim(self):
        report = {"groups": {"next": {"7": {"completed": 50, "win_rate_pct": 80.0, "avg_estimated_net_pct": 2.5}}}}
        result = inspect(report)
        self.assertFalse(result["independent_oos_verified"])
        self.assertEqual(result["groups"]["next"]["7"]["state"], "OBSERVED_THRESHOLD_MET")

    def test_reject_boolean_completed(self):
        report = {"groups": {"next": {"3": {"completed": True, "win_rate_pct": 90}}}}
        self.assertEqual(inspect(report)["groups"]["next"]["3"]["state"], "INVALID")

    def test_high_win_rate_negative_expectancy_is_not_promoted(self):
        report = {"groups": {"attack": {"3": {
            "completed": 100, "win_rate_pct": 80.0, "avg_estimated_net_pct": -1.2}}}}
        self.assertEqual(inspect(report)["groups"]["attack"]["3"]["state"], "UNDERPERFORMING")

    def test_missing_expectancy_blocks_positive_label(self):
        report = {"groups": {"attack": {"3": {"completed": 100, "win_rate_pct": 80.0}}}}
        self.assertEqual(inspect(report)["groups"]["attack"]["3"]["state"], "INSUFFICIENT_EVIDENCE")

    def test_all_short_horizon_groups_negative(self):
        report = {"groups": {
            "attack": {"3": {"completed": 62, "win_rate_pct": 25.81, "avg_estimated_net_pct": -3.778}},
            "monster": {"7": {"completed": 54, "win_rate_pct": 22.22, "avg_estimated_net_pct": -10.893}}}}
        risk = inspect(report)["short_horizon_risk"]
        self.assertEqual(risk["assessment"], "REVIEW_ALL_SHORT_HORIZON_SIGNALS")
        self.assertEqual(risk["underperforming"], 2)
        self.assertFalse(risk["automatic_trade_block"])

    def test_insufficient_data_not_counted_as_negative(self):
        report = {"groups": {"attack": {"3": {
            "completed": 2, "win_rate_pct": 0.0, "avg_estimated_net_pct": -3.0}}}}
        self.assertEqual(inspect(report)["short_horizon_risk"]["evaluated"], 0)
