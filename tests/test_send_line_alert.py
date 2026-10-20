"""Guard against stale or thin intraday LINE alerts."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.send_line_alert import trusted_live, build_alert

TZ = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 10, 20, 10, 15, tzinfo=TZ)


def feed():
    return {
        "data_date": "2026-10-20",
        "updated_at": "2026-10-20 10:00",
        "market": {
            "mode": "盤中即時",
            "stale": False,
            "live_valid": True,
            "live_count": 650,
        },
        "risk": {"level": "red", "score": 85, "reasons": ["測試風險"]},
    }


class IntradayLineAlertTests(unittest.TestCase):
    def test_verified_live_feed_can_build_risk_alert(self):
        self.assertTrue(trusted_live(feed(), NOW))
        self.assertEqual(build_alert(feed(), NOW)["edition"], "intraday_risk")

    def test_stale_or_unverified_feed_never_sends(self):
        mutations = [
            ("data_date", "2026-10-19"),
            ("updated_at", "2026-10-20 09:00"),
        ]
        for key, value in mutations:
            with self.subTest(key=key):
                f = feed()
                f[key] = value
                self.assertIsNone(build_alert(f, NOW))
        for key, value in [
            ("live_valid", False), ("live_count", 499),
            ("stale", True), ("mode", "今日收盤")
        ]:
            with self.subTest(key=key):
                f = feed()
                f["market"][key] = value
                self.assertIsNone(build_alert(f, NOW))

    def test_after_close_does_not_send_intraday_alert(self):
        self.assertIsNone(build_alert(feed(), datetime(2026, 10, 20, 14, 0, tzinfo=TZ)))


if __name__ == "__main__":
    unittest.main()
