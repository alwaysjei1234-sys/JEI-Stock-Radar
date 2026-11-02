import unittest
from scripts.update_system import calc_backtest


class BacktestDisclosureTests(unittest.TestCase):
    def test_gross_hit_rate_cannot_satisfy_oos_threshold(self):
        history = [{"signals": [{"code": "2330", "price": 100}],
                    "prices": {"2330": 100 + i * 5}} for i in range(12)]
        result = calc_backtest(history, {})
        self.assertEqual(result["hit3"], 100)
        self.assertFalse(result["validation"]["threshold_80_met"])
        self.assertFalse(result["validation"]["costs_included"])
        self.assertEqual(result["validation"]["qualified_oos_closed_trades"], 0)

    def test_empty_or_degraded_feed_retains_evidence_warning(self):
        result = calc_backtest([], {})
        self.assertIsNone(result["hit3"])
        self.assertEqual(result["samples"], 0)
        self.assertEqual(result["validation"]["status"], "insufficient_evidence")
