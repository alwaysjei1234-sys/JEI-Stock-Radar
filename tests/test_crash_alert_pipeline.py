"""P0: crash alerts must run from real feed writers, not schedules only."""
from pathlib import Path
import re
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.send_line_alert import build_alert, live_gate_reasons

ROOT=Path(__file__).resolve().parents[1]
PRIMARY=(ROOT/".github/workflows/update-system.yml").read_text(encoding="utf-8")
RECOVERY=(ROOT/".github/workflows/recover-stale-market-feed.yml").read_text(encoding="utf-8")
TZ=ZoneInfo("Asia/Taipei")


class CrashAlertPipelineTests(unittest.TestCase):
    def test_successful_primary_push_dispatches_risk_notifications(self):
        self.assertIn("Dispatch verified high-risk LINE alert after every successful feed publish", PRIMARY)
        tail=PRIMARY.split("Dispatch verified high-risk LINE alert after every successful feed publish",1)[1]
        self.assertIn("github.event_name == 'push'",tail.split("\n      - name:",1)[0])
        self.assertIn("github.event_name == 'schedule'",tail.split("\n      - name:",1)[0])
        self.assertIn("github.event_name == 'workflow_dispatch'",tail.split("\n      - name:",1)[0])
        self.assertIn("python -m scripts.send_line_alert --result-path",tail)
        self.assertIn("JEI_LINE_CHANNEL_ACCESS_TOKEN: ${{ secrets.JEI_LINE_CHANNEL_ACCESS_TOKEN }}",tail)
        self.assertIn("JEI_LINE_USER_ID: ${{ secrets.JEI_LINE_USER_ID }}",tail)

    def test_backup_dispatches_with_same_verified_market_guard(self):
        tail=RECOVERY.split("Dispatch any verified red risk after recovery or fresh-feed check",1)[1]
        self.assertIn("if: success()",tail.split("\n      - name:",1)[0])
        self.assertIn("python -m scripts.send_line_alert --result-path",tail)
        self.assertNotIn("github.event_name == 'schedule'",tail)
        self.assertIn("if-no-files-found: warn",tail)

    def test_results_must_be_preserved_for_push_and_backup(self):
        marker="Preserve intraday LINE decision and API acceptance"
        text=PRIMARY.split(marker,1)[1]
        self.assertIn("github.event_name == 'push'",text.split("\n      - name:",1)[0])
        self.assertIn("if: always()",RECOVERY.split("Preserve fallback alert decision and LINE API acceptance",1)[1])

    def test_a_realistic_verified_crash_triggers_red_alert(self):
        now=datetime(2026,11,16,9,44,tzinfo=TZ)
        feed={
          "data_date":"2026-11-16","updated_at":"2026-11-16 09:39",
          "market":{"mode":"盤中即時","live_valid":True,"stale":False,
                    "historical_readonly":False,"live_count":1225,
                    "close_count":1973,"no_new_picks":False},
          "risk":{"level":"red","score":100,"as_of":"2026-11-16",
                  "actionable":True,"label":"高風險防守",
                  "reasons":["加權指數 -2.94%","下跌家數 908","跌逾5% 273"]}}
        self.assertEqual(live_gate_reasons(feed,now),[])
        alert=build_alert(feed,now)
        self.assertEqual(alert["edition"],"intraday_risk")
        self.assertIn("🔴",alert["title"])
        self.assertIn("100/100",alert["blocks"][0]["items"][0])
        # Even a valid RED risk must NEVER notify if based on stale quotes.
        self.assertIsNone(build_alert(feed,now.replace(hour=9,minute=51)))

    def test_no_disable_switch_or_recipient_bypass(self):
        for src in (PRIMARY,RECOVERY):
            self.assertRegex(src,r"JEI_LINE_ENABLED:\s*\$\{\{ vars\.JEI_LINE_ENABLED \}\}")
            self.assertIn("JEI_LINE_ALERTS_ENABLED",src)
            self.assertIn("vars.JEI_LINE_ALERTS_ENABLED != 'false'",src)


if __name__=="__main__":
    unittest.main()
