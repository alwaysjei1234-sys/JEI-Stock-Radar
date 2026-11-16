"""Guard current-date institutional reports from blocking the live-price refresh."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from scripts.update_system import same_day_institutional_report_available

TZ=ZoneInfo("Asia/Taipei")


class SameDayInstitutionalReleaseTests(unittest.TestCase):
    def test_weekday_premarket_and_live_trading_do_not_request_daily_report(self):
        for hour,minute in ((8,31),(8,59),(9,0),(10,5),(12,0),(13,29)):
            with self.subTest(hour=hour,minute=minute):
                stamp=datetime(2026,11,16,hour,minute,tzinfo=TZ)
                self.assertFalse(same_day_institutional_report_available(stamp))

    def test_after_market_close_may_request_strict_same_date_report(self):
        for h,m in ((13,30),(14,45),(16,0),(23,50)):
            with self.subTest(time=(h,m)):
                self.assertTrue(same_day_institutional_report_available(
                    datetime(2026,11,16,h,m,tzinfo=TZ)))

    def test_holiday_and_weekend_never_request_same_date_report(self):
        for date in ((2026,11,15),(2026,12,25),(2026,10,26)):
            self.assertFalse(same_day_institutional_report_available(
                datetime(*date,14,15,tzinfo=TZ)))

    def test_timezone_conversion_never_uses_utc_wall_clock(self):
        clock=datetime.fromisoformat("2026-11-16T04:45:00Z".replace("Z","+00:00"))
        self.assertFalse(same_day_institutional_report_available(clock))
        clock=datetime.fromisoformat("2026-11-16T05:31:00+00:00")
        self.assertTrue(same_day_institutional_report_available(clock))

    def test_naive_clock_rejected(self):
        with self.assertRaisesRegex(ValueError,"timezone-aware"):
            same_day_institutional_report_available(datetime(2026,11,16,9,0))


if __name__=="__main__":
    unittest.main()
