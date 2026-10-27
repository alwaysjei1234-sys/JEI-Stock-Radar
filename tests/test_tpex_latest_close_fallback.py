import unittest
from datetime import date
from unittest.mock import patch

from scripts.update_system import fetch_tpex_daily, parse_tpex_latest_snapshot


class TpexLatestCloseFallbackTests(unittest.TestCase):
    def snapshot(self, day="1151027", n=550):
        return [
            {"Date": day, "SecuritiesCompanyCode": str(3000 + i), "Close": "42.50"}
            for i in range(n)
        ]

    def test_valid_official_latest_close(self):
        rows = parse_tpex_latest_snapshot(self.snapshot(), date(2026, 10, 27))
        self.assertEqual(len(rows), 550)
        self.assertEqual(rows[0]["close"], 42.5)

    def test_reject_previous_trading_day(self):
        with self.assertRaisesRegex(RuntimeError, "date mismatch"):
            parse_tpex_latest_snapshot(self.snapshot("1151022"), date(2026, 10, 27))

    def test_reject_partial_response(self):
        with self.assertRaisesRegex(RuntimeError, "coverage too low"):
            parse_tpex_latest_snapshot(self.snapshot(n=30), date(2026, 10, 27))

    def test_fallback_from_empty_historical_endpoint(self):
        with patch("scripts.update_system.fetch_json_fast",
                   side_effect=[{"aaData": []}, self.snapshot()]) as fetch:
            rows = fetch_tpex_daily(date(2026, 10, 27))
        self.assertEqual(len(rows), 550)
        self.assertIn("tpex_mainboard_daily_close_quotes", fetch.call_args_list[-1].args[0])

    def test_fallback_never_labels_prior_close_as_today(self):
        with patch("scripts.update_system.fetch_json_fast",
                   side_effect=[{"aaData": []}, self.snapshot("1151022")]):
            with self.assertRaisesRegex(RuntimeError, "date mismatch"):
                fetch_tpex_daily(date(2026, 10, 27))


if __name__ == "__main__":
    unittest.main()
