"""Regression tests: only same-day executed MIS trades qualify as live."""
import unittest
from datetime import datetime
from unittest.mock import patch

from scripts.update_system import enrich_live, live_price, TZ


class LiveQuoteTests(unittest.TestCase):
    def test_last_trade_only(self):
        self.assertIsNone(live_price({"y": "100", "b": "101_102", "a": "103"}))
        self.assertIsNone(live_price({"z": "-"}))
        self.assertEqual(live_price({"z": "101.5", "y": "100"}), 101.5)

    def test_same_day_trade_updates_close(self):
        rows = [{"code": "2330", "market": "TWSE", "close": 100.0, "pct": 0.0}]
        quote = {"c": "2330", "d": "20261021", "t": "09:30:05", "z": "105", "y": "100"}
        with patch("scripts.update_system.fetch_mis_channels", return_value=[quote]):
            result, count, _, errors, _ = enrich_live(rows, asof=datetime(2026, 10, 21, 10, 0, tzinfo=TZ))
        self.assertEqual(count, 1)
        self.assertEqual(result[0]["close"], 105)
        self.assertTrue(result[0]["live"])
        self.assertFalse(errors)

    def test_reject_old_date_nontrading_time_and_bid_only(self):
        base = {"c": "2330", "d": "20261021", "t": "09:30:05", "z": "105", "y": "100"}
        cases = [{"d": "20261020"}, {"t": "08:59:59"}, {"t": "13:31:00"},
                 {"z": "-", "b": "105_100"}]
        for changes in cases:
            with self.subTest(changes=changes):
                rows = [{"code": "2330", "market": "TWSE", "close": 100.0}]
                with patch("scripts.update_system.fetch_mis_channels", return_value=[dict(base, **changes)]):
                    result, count, _, _, _ = enrich_live(rows, asof=datetime(2026, 10, 21, 10, 0, tzinfo=TZ))
                self.assertEqual(count, 0)
                self.assertEqual(result[0]["close"], 100.0)
                self.assertFalse(result[0].get("live", False))


if __name__ == "__main__":
    unittest.main()
