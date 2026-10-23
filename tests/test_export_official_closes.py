"""Regression tests for full-market official paper close exports."""
import unittest

from scripts.export_official_closes import export_archive


DAY = "2026-10-22"


class ExportOfficialCloseTests(unittest.TestCase):
    def setUp(self):
        self.quotes = {f"{1000+i:04d}": 10.5 + i for i in range(600)}
        self.daily = {
            "schema": 1,
            "kind": "official_daily_close",
            "days": {DAY: self.quotes},
        }

    def test_exports_only_valid_same_day_whole_market_closes(self):
        self.daily["days"][DAY]["BAD"] = 100
        self.daily["days"][DAY]["1100"] = True
        result = export_archive(self.daily, DAY)
        self.assertEqual(result["kind"], "official_daily_close")
        self.assertEqual(result["data_date"], DAY)
        self.assertEqual(result["coverage_count"], 600)
        self.assertEqual(len(result["days"][DAY]), 600)
        self.assertEqual(result["days"][DAY]["1000"], 10.5)
        self.assertNotIn("BAD", result["days"][DAY])
        self.assertNotIn("1100", result["days"][DAY])

    def test_rejects_unverified_format_missing_day_or_low_coverage(self):
        for invalid in [
            {"schema": 1, "kind": "proxy", "days": {DAY: self.quotes}},
            {"schema": 1, "kind": "official_daily_close", "days": {}},
            {"schema": 2, "kind": "official_daily_close", "days": {DAY: self.quotes}},
        ]:
            with self.subTest(invalid=invalid.get("kind")):
                with self.assertRaises(ValueError):
                    export_archive(invalid, DAY)
        small = {**self.daily, "days": {DAY: dict(list(self.quotes.items())[:499])}}
        with self.assertRaisesRegex(ValueError, "覆蓋不足"):
            export_archive(small, DAY)

    def test_rejects_invalid_dates(self):
        for day in ["", "2026-10-23x", "2026/10/22"]:
            with self.subTest(day=day), self.assertRaises(ValueError):
                export_archive(self.daily, day)


if __name__ == "__main__":
    unittest.main()
