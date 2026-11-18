"""Safety and transcription checks for historical, user-provided external screens.

These are NOT time-authenticated forward picks or official trading returns.
"""
import json
from collections import Counter
from pathlib import Path
import unittest

ARCHIVE = Path("data/research_evidence/external_watchlists_20260420.json")


class ExternalScreenshotCohortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(ARCHIVE.read_text(encoding="utf-8"))

    def test_retrospective_only_never_promoted_to_oos_or_live(self):
        d = self.data
        self.assertEqual(d["kind"], "external_historical_screenshot_candidates")
        self.assertEqual(d["forecast_entry_date_as_displayed"], "2026-04-20")
        self.assertEqual(d["screenshots_provided_to_chat_on"], "2026-11-18")
        for field in (
            "authentic_generation_timestamp_verified", "price_quote_date_verified",
            "independent_out_of_sample", "eligible_for_live_trading_signals",
            "eligible_for_jei_strategy_promotion",
        ):
            self.assertIs(d[field], False, field)
        self.assertIn("do_not_average", d["score_comparability"])

    def test_four_screens_have_their_own_scores_and_all_46_rows(self):
        d = self.data
        groups = d["strategies"]
        self.assertEqual(
            {g["strategy"]: len(g["rows"]) for g in groups},
            {"vcp": 10, "bollinger_breakout": 12,
             "pattern_breakout": 12, "sector_linkage": 12})
        self.assertEqual(d["strategy_count"], len(groups))
        self.assertEqual(d["row_count"], sum(len(g["rows"]) for g in groups))
        for group in groups:
            codes = [r["ticker"] for r in group["rows"]]
            self.assertEqual(len(codes), len(set(codes)))
            for row in group["rows"]:
                self.assertRegex(row["ticker"], r"^\d{4}$")
                self.assertTrue(row["name"])
                self.assertGreater(row["reference_price_displayed"], 0)
                self.assertTrue(0 <= row["model_score_displayed"] <= 100)
                # No synthetic fills, future returns, or unverified quote dates.
                self.assertFalse(set(row) & {
                    "return_3d", "return_7d", "return_15d", "return_30d",
                    "actual_entry", "actual_exit", "verified_close", "entry_date"})

    def test_cross_model_overlap_is_not_collapsed_or_score_averaged(self):
        all_rows = [(g["strategy"], row) for g in self.data["strategies"]
                    for row in g["rows"]]
        counts = Counter(row["ticker"] for _, row in all_rows)
        overlap = sorted(code for code, count in counts.items() if count > 1)
        self.assertEqual(overlap, ["2383", "2501"])
        self.assertEqual(self.data["overlap_tickers"], overlap)
        self.assertEqual(self.data["unique_ticker_count"], len(counts))
        self.assertEqual(counts["2383"], 2)
        self.assertEqual(counts["2501"], 2)
        self.assertNotEqual(
            {strategy: row["model_score_displayed"] for strategy, row in all_rows
             if row["ticker"] == "2501"}["vcp"],
            {strategy: row["model_score_displayed"] for strategy, row in all_rows
             if row["ticker"] == "2501"}["pattern_breakout"])


if __name__ == "__main__":
    unittest.main()
