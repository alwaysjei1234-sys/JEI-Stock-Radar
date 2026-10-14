"""Quote-source regression tests: never treat previous-day MIS snapshots as today's prices."""
import importlib.util
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update_system.py"
SPEC = importlib.util.spec_from_file_location("jei_market_update", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class QuoteFreshnessTests(unittest.TestCase):
    ASOF = datetime(2026, 10, 14, 10, 15, tzinfo=ZoneInfo("Asia/Taipei"))

    def run_snapshot(self, quote_day, index_day=None):
        stock = {"code": "2330", "name": "台積電", "market": "TWSE", "date": "1151013",
                 "close": 900.0, "pct": 0.0}
        def fake_mis(channels):
            if channels == ["tse_t00.tw"]:
                return [{"d": index_day if index_day is not None else quote_day,
                         "y": "10000", "z": "10100"}]
            return [{"c": "2330", "n": "台積電", "d": quote_day,
                     "t": "10:15:00", "y": "900", "z": "920", "v": "4500"}]
        with patch.object(MOD, "fetch_mis_channels", side_effect=fake_mis):
            result, count, taiex, errors = MOD.enrich_live([stock], asof=self.ASOF)
        return result[0], count, taiex, errors

    def test_yesterday_quote_never_overwrites_official_close(self):
        row, count, taiex, _ = self.run_snapshot("20261013")
        self.assertEqual(count, 0)
        self.assertEqual(row["close"], 900.0)
        self.assertNotIn("live", row)
        self.assertIsNone(taiex)

    def test_today_quote_can_be_used_during_regular_session(self):
        row, count, taiex, _ = self.run_snapshot("20261014")
        self.assertEqual(count, 1)
        self.assertEqual(row["close"], 920.0)
        self.assertTrue(row["live"])
        self.assertAlmostEqual(taiex, 1.0)

    def test_missing_exchange_date_is_not_live(self):
        row, count, taiex, _ = self.run_snapshot("")
        self.assertEqual(count, 0)
        self.assertEqual(row["close"], 900.0)
        self.assertIsNone(taiex)

    def test_index_date_is_verified_separately(self):
        _, count, taiex, _ = self.run_snapshot("20261014", index_day="20261013")
        self.assertEqual(count, 1)
        self.assertIsNone(taiex)


if __name__ == "__main__":
    unittest.main()
