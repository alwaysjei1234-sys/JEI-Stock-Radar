import unittest
from datetime import date

from scripts.validate_market_session import validate_session


class MarketSessionValidationTests(unittest.TestCase):
    def feed(self, day="2026-10-22"):
        return {
            "updated_at": "2026-10-27 14:20",
            "data_date": day,
            "summary": "交易日官方收盤待驗證",
            "risk": {"actionable": False},
            "market": {
                "session_status": "交易日資料待驗證",
                "mode": "最近收盤",
                "stale": True,
                "historical_readonly": True,
                "next_expected_session": None,
                "brief": "最近有效收盤，今日選股暫停",
            },
        }

    def test_reopened_market_clears_prior_holiday(self):
        self.assertTrue(validate_session(self.feed(), date(2026, 10, 27)))

    def test_old_holiday_status_is_rejected(self):
        feed = self.feed()
        feed["market"]["session_status"] = "休市"
        feed["summary"] = "今日休市：光復節補假"
        with self.assertRaisesRegex(ValueError, "Stale holiday"):
            validate_session(feed, date(2026, 10, 27))

    def test_old_next_session_date_is_rejected(self):
        feed = self.feed()
        feed["market"]["next_expected_session"] = "2026-10-27"
        with self.assertRaisesRegex(ValueError, "next session"):
            validate_session(feed, date(2026, 10, 27))

    def test_historical_close_cannot_be_fresh(self):
        feed = self.feed()
        feed["market"]["stale"] = False
        with self.assertRaisesRegex(ValueError, "read-only"):
            validate_session(feed, date(2026, 10, 27))

    def test_confirmed_holiday_is_valid(self):
        feed = self.feed()
        feed["market"]["session_status"] = "休市"
        feed["summary"] = "今日休市：光復節補假"
        self.assertTrue(validate_session(feed, date(2026, 10, 26)))

    def test_current_verified_close(self):
        feed = self.feed("2026-10-27")
        feed["market"].update({"mode": "今日收盤", "stale": False, "historical_readonly": False})
        self.assertTrue(validate_session(feed, date(2026, 10, 27)))


if __name__ == "__main__":
    unittest.main()
