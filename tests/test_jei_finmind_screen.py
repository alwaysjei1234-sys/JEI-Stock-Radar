import unittest
from tools.jei_finmind_screen import screen

BASE = dict(ticker="2882", sector="金融", trade_date="2026-11-06",
            close="45", ma60="50", trust_buy_shares_20d="6000000",
            revenue_yoy_pct="25", revenue_publish_date="2026-11-05")

class FinmindScreenTests(unittest.TestCase):
    def test_match(self):
        self.assertEqual(len(screen([BASE], "2026-11-06")["matches"]), 1)

    def test_not_yet_published(self):
        row = {**BASE, "revenue_publish_date": "2026-11-07"}
        result = screen([row], "2026-11-06")
        self.assertFalse(result["matches"])
        self.assertEqual(result["rejected_rows"][0]["reason"], "future_or_unpublished_data")

    def test_threshold_strict(self):
        row = {**BASE, "trust_buy_shares_20d": "5000000"}
        self.assertFalse(screen([row], "2026-11-06")["matches"])

    def test_nan_rejected(self):
        row = {**BASE, "ma60": "nan"}
        self.assertEqual(screen([row], "2026-11-06")["rejected_rows"][0]["reason"], "non_finite_values")

    def test_wrong_sector(self):
        self.assertFalse(screen([{**BASE, "sector": "電子"}], "2026-11-06")["matches"])

if __name__ == "__main__":
    unittest.main()
