"""Safety tests for JEI LINE intraday alerts. Never use actual LINE credentials."""
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from scripts import send_line_alert as alert

TZ = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 10, 16, 10, 15, tzinfo=TZ)


def feed(**changes):
    base = {
        "data_date": "2026-10-16",
        "updated_at": "2026-10-16 10:10",
        "market": {"mode": "盤中即時", "stale": False, "live_valid": True, "live_count": 1580},
        "risk": {"level": "red", "score": 91, "label": "高度警戒", "reasons": ["上漲家數縮減"]},
        "monster": [{"code": "2344", "name": "測試強勢股", "score": 97, "change_pct": 5.2, "price": 50.5}],
    }
    return {**base, **changes}


class LineAlertTests(unittest.TestCase):
    def test_critical_risk_has_verified_date_and_no_private_positions(self):
        snapshot = feed(holdings={"PERSONAL_SECRET": {"cost": 987654}})
        result = alert.build_alert(snapshot, NOW)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["edition"], "intraday_risk")
        self.assertIn("高風險", result["title"])
        self.assertNotIn("PERSONAL_SECRET", str(result))
        self.assertNotIn("987654", str(result))

    def test_reject_stale_old_or_thin_market_data(self):
        base = feed()
        variants = [
            {**base, "data_date": "2026-10-15"},
            {**base, "updated_at": "2026-10-16 09:00"},
            {**base, "updated_at": "2026-10-16 10:30"},
            {**base, "market": {**base["market"], "stale": True}},
            {**base, "market": {**base["market"], "live_valid": False}},
            {**base, "market": {**base["market"], "live_count": 499}},
            {**base, "market": {**base["market"], "mode": "今日收盤"}},
            {**base, "market": {**base["market"], "live_count": True}},
        ]
        for s in variants:
            with self.subTest(snapshot=s):
                self.assertIsNone(alert.build_alert(s, NOW))
        self.assertIsNone(alert.build_alert(base, NOW.replace(hour=8, minute=55)))
        self.assertIsNone(alert.build_alert(base, NOW.replace(hour=13, minute=31)))
        self.assertIsNone(alert.build_alert(base, NOW + timedelta(days=1)))

    def test_normal_market_only_high_threshold_momentum(self):
        normal = feed(risk={"level": "green", "score": 26, "reasons": []})
        result = alert.build_alert(normal, NOW)
        self.assertIn("強勢股", result["title"])
        self.assertEqual(result["edition"], "intraday_momentum")
        self.assertIn("2344", str(result))
        self.assertNotIn("漲停預測", str(result).replace("非漲停預測", ""))
        slow = dict(normal, monster=[{"code": "2344", "name": "慢股", "score": 92, "change_pct": 3, "price": 50}])
        self.assertIsNone(alert.build_alert(slow, NOW))
        risky = dict(normal, risk={"level": "yellow", "score": 60})
        self.assertIsNone(alert.build_alert(risky, NOW))

    def test_push_disabled_by_default_even_when_eligible(self):
        with patch.dict("os.environ", {}, clear=True), patch.object(alert, "push") as push, patch.object(alert, "build_alert") as build:
            alert.main()
            push.assert_not_called()
            build.assert_not_called()

    def test_scheduled_line_alert_activation_requires_existing_global_opt_in(self):
        from pathlib import Path
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/update-system.yml").read_text(encoding="utf-8")
        self.assertIn("vars.JEI_LINE_ENABLED == 'true'", workflow,
                      "a successful LINE test does not override the owner's master opt-in")
        self.assertIn("vars.JEI_LINE_ALERTS_ENABLED != 'false'", workflow,
                      "intraday alerts must have a separate explicit off switch")
        self.assertIn("if: github.event_name == 'schedule'", workflow,
                      "a code push must not send a real market warning")
        self.assertIn("python -m scripts.send_line_alert", workflow)

    def test_alert_can_reuse_daily_line_quota_gate(self):
        self.assertEqual(alert.push.__module__, "scripts.send_line_brief")
        self.assertEqual(alert.can_send.__module__, "scripts.send_line_brief")
        result = alert.build_alert(feed(), NOW)
        from scripts import send_line_brief
        self.assertTrue(send_line_brief.can_send(result, "intraday_risk", NOW, "true", "example-token", "U" + "a" * 32)[0])
        self.assertFalse(send_line_brief.can_send(result, "close", NOW, "true", "example-token", "U" + "a" * 32)[0])
        momentum = alert.build_alert(feed(risk={"level":"green", "score":26}), NOW)
        self.assertEqual(momentum["edition"], "intraday_momentum")
        self.assertNotEqual(result["edition"], momentum["edition"], "early momentum cannot suppress later crash warning")
        self.assertIn('report["date"]+"/"+edition', __import__("inspect").getsource(send_line_brief.push))


if __name__ == "__main__":
    unittest.main()
