"""No-network consistency checks for two existing TWSE collection paths."""
import unittest
from scripts.crosscheck_official_closes import compare_archive


def fixture():
    daily = {"schema": 1, "kind": "official_daily_close",
             "days": {"2026-11-02": {"1101": 28.1},
                      "2026-11-03": {"1101": 27.7}}}
    snap = {"code": "1101", "market": "TWSE",
            "source": "TWSE STOCK_DAY fetched via HTTPS; corporate actions not adjusted",
            "adjusted_for_corporate_actions": False,
            "prices": [{"date": "2026-11-02", "close": 28.1},
                       {"date": "2026-11-03", "close": 27.7}]}
    return daily, snap


class CloseCrossCheckTests(unittest.TestCase):
    def test_same_date_prices_consistent_without_upgrading_trust(self):
        daily, snap = fixture()
        r = compare_archive(daily, [snap])
        self.assertTrue(r["ok"])
        self.assertEqual(r["checked_count"], 2)
        self.assertFalse(r["live_trading_verified"])
        self.assertFalse(r["upgrades_live_valid"])
        self.assertTrue(r["same_exchange_not_independent"])

    def test_mismatch_stays_visible_and_cannot_be_overwritten(self):
        daily, snap = fixture()
        snap["prices"][1]["close"] = 30.0
        r = compare_archive(daily, [snap])
        self.assertFalse(r["ok"])
        self.assertEqual(r["status"], "conflict")
        self.assertEqual(r["conflicts"][0]["date"], "2026-11-03")
        self.assertEqual(daily["days"]["2026-11-03"]["1101"], 27.7)

    def test_missing_day_is_not_assumed_to_match(self):
        daily, snap = fixture()
        snap["prices"] = [{"date": "2026-11-04", "close": 27.8}]
        r = compare_archive(daily, [snap])
        self.assertEqual(r["status"], "no_overlap")
        self.assertFalse(r["ok"])

    def test_reject_foreign_source_adjustment_and_duplicate_conflict(self):
        daily, snap = fixture()
        snap["market"] = "TPEx"
        with self.assertRaises(ValueError):
            compare_archive(daily, [snap])
        snap["market"] = "TWSE"
        snap["adjusted_for_corporate_actions"] = True
        with self.assertRaises(ValueError):
            compare_archive(daily, [snap])
        snap["adjusted_for_corporate_actions"] = False
        snap["prices"].append({"date": "2026-11-03", "close": 27.8})
        with self.assertRaises(ValueError):
            compare_archive(daily, [snap])

    def test_missing_symbol_reports_gap_not_consistency(self):
        daily, snap = fixture()
        daily["days"]["2026-11-03"].pop("1101")
        r = compare_archive(daily, [snap])
        self.assertEqual(r["missing_in_archive"], 1)
        self.assertEqual(r["checked_count"], 1)


if __name__ == "__main__":
    unittest.main()
