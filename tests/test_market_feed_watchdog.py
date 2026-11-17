import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from scripts.market_feed_watchdog import assess

TZ = ZoneInfo("Asia/Taipei")
NOW = datetime(2026,11,16,9,1,tzinfo=TZ)


def feed(day="2026-11-16", time="08:55"):
    return {"schema":1,"data_date":"2026-11-13",
            "market":{"status_updated_at":f"{day} {time}",
                      "live_valid":False,"historical_readonly":True}}


class MarketFeedWatchdogTests(unittest.TestCase):
    def test_previous_day_monitor_triggers_without_claiming_live(self):
        expected, reason=assess(feed("2026-11-13","23:47"),NOW)
        self.assertTrue(expected)
        self.assertEqual(reason,"feed_last_checked_on_previous_day")

    def test_preopen_missing_0845_schedule_triggers_fallback(self):
        needed,reason=assess(feed("2026-11-16","05:53"),
                             datetime(2026,11,16,8,51,tzinfo=TZ))
        self.assertTrue(needed)
        self.assertIn("stalled",reason)

    def test_recent_preopen_checked_at_is_good_even_historical_source(self):
        needed, reason=assess(feed(),NOW)
        self.assertFalse(needed)
        self.assertIn("recent", reason)
        # The watchdog never upgrades an old close into valid live ticks:
        self.assertFalse(feed()["market"]["live_valid"])

    def test_exact_freshness_boundary_and_one_minute_over(self):
        expected, _=assess(feed(time="08:45"), NOW)
        self.assertFalse(expected)
        expected, _=assess(feed(time="08:44"), NOW)
        self.assertTrue(expected)

    def test_live_feed_frozen_since_0925_triggers_recovery_at_noon(self):
        stalled = feed("2026-11-17", "09:25")
        stalled["data_date"] = "2026-11-17"
        stalled["market"].update(live_valid=True, live_count=1315, live_coverage_pct=66.6)
        needed, reason = assess(stalled, datetime(2026, 11, 17, 12, 11, tzinfo=TZ))
        self.assertTrue(needed)
        self.assertEqual(reason, "feed_check_stalled_166m")

    def test_future_timestamp_is_not_accepted(self):
        expected,reason=assess(feed(time="09:05"),NOW)
        self.assertTrue(expected)
        self.assertEqual(reason,"future_dated_feed_check_timestamp")

    def test_missing_malformed_stamps_are_a_failure(self):
        for value in (None,"bad","2026-11-16 99:99",123):
            data=feed()
            data["market"]["status_updated_at"]=value
            data["market"].pop("last_checked_at",None)
            with self.subTest(value=value):
                needed,_=assess(data,NOW)
                self.assertTrue(needed)

    def test_no_refresh_on_weekend_and_offhours(self):
        for clock in (datetime(2026,11,15,9,0,tzinfo=TZ),
                      datetime(2026,11,16,8,29,tzinfo=TZ),
                      datetime(2026,11,16,20,0,tzinfo=TZ)):
            with self.subTest(clock=clock):
                needed,_=assess(feed("2026-11-13","05:53"),clock)
                self.assertFalse(needed)

    def test_market_holiday_disables_recovery(self):
        needed,reason=assess(feed(),datetime(2026,12,25,9,15,tzinfo=TZ))
        self.assertFalse(needed)
        self.assertEqual(reason,"verified_exchange_closure")

    def test_untrusted_json_fails_closed(self):
        for data in (None,{},[],{"market":{}},{"market":None}):
            with self.subTest(data=data):
                needed,_=assess(data,NOW)
                self.assertTrue(needed)

    def test_utc_converted_to_taipei(self):
        utc=datetime.fromisoformat("2026-11-16T01:01:00+00:00")
        self.assertEqual(assess(feed(),NOW),assess(feed(),utc))

    def test_naive_clock_rejected(self):
        with self.assertRaisesRegex(ValueError,"timezone"):
            assess(feed(),datetime(2026,11,16,9,1))


if __name__=="__main__":
    unittest.main()
