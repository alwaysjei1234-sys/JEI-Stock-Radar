import unittest
from scripts.pattern_signals import build_pattern_signals

def fixture(n=21, count=320, jump=True):
    codes = [str(1000 + i) for i in range(count)]
    days = []
    for i in range(n):
        price = 10.0 + i * 0.03
        if i == n - 1 and jump:
            price *= 1.12
        days.append({"date": f"2026-10-{i+1:02d}", "prices": {c: price for c in codes}})
    stocks = {c: {"name": "測試", "close": days[-1]["prices"][c]} for c in codes}
    sectors = {c: "測試族群" for c in codes}
    stats = [{"name": "測試族群", "score": 80, "breadth": 75}]
    return days, stocks, sectors, stats

class StrategyRadarTests(unittest.TestCase):
    def test_requires_twenty_one_snapshot_sessions(self):
        h, stocks, sector, stats = fixture(n=20)
        result = build_pattern_signals(h, stocks, sector, stats)
        self.assertEqual(result["status"], "insufficient")
        self.assertEqual(result["signals"]["breakout"], [])

    def test_breakout_uses_past_closes_and_never_promises_return(self):
        h, stocks, sector, stats = fixture()
        result = build_pattern_signals(h, stocks, sector, stats, asof=h[-1]["date"])
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["coverage"], 320)
        self.assertEqual(len(result["signals"]["breakout"]), 12)
        self.assertIn("未驗證成交量", result["signals"]["breakout"][0]["reason"])
        self.assertNotIn("probability", result["signals"]["breakout"][0])
        self.assertEqual(result["signals"]["breakout"][0]["data_date"], h[-1]["date"])

    def test_chart_series_contains_only_dated_observed_closes(self):
        h, stocks, sector, stats = fixture()
        result = build_pattern_signals(h, stocks, sector, stats)
        row = result["signals"]["breakout"][0]
        series = row["close_series"]
        self.assertEqual(len(series), 21)
        self.assertEqual([point["date"] for point in series], [snap["date"] for snap in h])
        self.assertEqual([point["close"] for point in series],
                         [round(snap["prices"][row["code"]], 4) for snap in h])
        self.assertNotIn("open", series[-1])
        self.assertNotIn("volume", series[-1])

    def test_reference_levels_use_prior_closes_only(self):
        h, stocks, sector, stats = fixture()
        result = build_pattern_signals(h, stocks, sector, stats)
        row = result["signals"]["breakout"][0]
        prior = [snap["prices"][row["code"]] for snap in h[:-1]]
        levels = row["reference_levels"]
        self.assertAlmostEqual(levels["prior_20_close_high"], round(max(prior), 4))
        self.assertAlmostEqual(levels["prior_20_close_low"], round(min(prior), 4))
        self.assertAlmostEqual(levels["prior_20_close_mean"], round(sum(prior)/20, 4))
        self.assertNotIn("stop_loss", row)
        self.assertNotIn("entry_price", row)

    def test_rejects_mismatched_market_date(self):
        h, stocks, sector, stats = fixture()
        result = build_pattern_signals(h, stocks, sector, stats, asof="2026-10-31")
        self.assertEqual(result["status"], "date_mismatch")
        self.assertTrue(all(not rows for rows in result["signals"].values()))

    def test_partial_quote_coverage_disables_all_strategies(self):
        h, stocks, sector, stats = fixture(count=299)
        result = build_pattern_signals(h, stocks, sector, stats)
        self.assertEqual(result["status"], "coverage_insufficient")
        self.assertTrue(all(not rows for rows in result["signals"].values()))

    def test_invalid_historical_price_is_not_analyzed(self):
        h, stocks, sector, stats = fixture()
        h[-5]["prices"]["1000"] = None
        result = build_pattern_signals(h, stocks, sector, stats)
        self.assertEqual(result["coverage"], 319)
        self.assertNotIn("1000", [x["code"] for x in result["signals"]["breakout"]])

if __name__ == "__main__":
    unittest.main()
