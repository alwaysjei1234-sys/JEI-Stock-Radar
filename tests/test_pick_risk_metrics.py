import unittest
from scripts.pick_risk_metrics import max_close_drawdown, duplicate_signal_summary


class RiskMetricsTests(unittest.TestCase):
    def test_drawdown_from_signal_and_later_peak(self):
        self.assertEqual(max_close_drawdown(100, [110, 99, 120, 90]), -25.0)

    def test_flat_closes(self):
        self.assertEqual(max_close_drawdown(100, [100, 100]), 0.0)

    def test_invalid_close_is_rejected(self):
        with self.assertRaises(ValueError):
            max_close_drawdown(100, [101, None])

    def test_duplicate_categories_not_unique_trades(self):
        rows = [
            {"day": "2026-10-21", "code": "2449", "group": "attack"},
            {"day": "2026-10-21", "code": "2449", "group": "monster"},
            {"day": "2026-10-22", "code": "2449", "group": "attack"},
        ]
        self.assertEqual(duplicate_signal_summary(rows), {
            "category_recommendations": 3,
            "unique_day_symbol_signals": 2,
            "cross_category_duplicates": 1,
        })


if __name__ == "__main__":
    unittest.main()
