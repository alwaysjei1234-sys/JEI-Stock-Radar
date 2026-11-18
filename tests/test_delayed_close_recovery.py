"""Cross-midnight GitHub cron delay must not lose yesterday's price archive.

These tests deliberately require no live network or LINE credentials.
"""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.build_daily_brief import build, recover_previous_close_archive
from scripts.send_line_brief import can_send

TZ=ZoneInfo("Asia/Taipei")


def at(day="2026-11-18",hour=3,minute=8):
    return datetime.fromisoformat(f"{day}T{hour:02}:{minute:02}:00+08:00")


def prices(day="2026-11-17",count=500):
    return {"schema":1,"kind":"official_daily_close","days":{
        day:{str(i+1000):float(i+1) for i in range(count)}
    }}


def prior():
    return {"schema":1,"morning":None,"close":{
        "edition":"close","status":"ready","date":"2026-11-13",
        "title":"older actual report","private_marker":"NEVER_EXPORT"
    },"checks":{}}


class MissedCloseRecoveryTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.feed=self.root/"system.json"
        self.paper=self.root/"paper.json"
        self.archive=self.root/"daily_prices.json"
        self.out=self.root/"brief.json"
        self.feed.write_text(json.dumps({
            "data_date":"2026-11-18",
            "market":{"mode":"盤中即時","stale":False,"live_valid":True,
                      "close_count":500,"status":"盤中"},
            "risk":{"label":"FABRICATED_INTRADAY_RISK","score":99,"reasons":["NEVER_REUSE"]},
            "attack":[{"name":"NEVER_REUSE_PICK"}],
            "holdings":{"PERSONAL":{"cost":100000,"name":"PRIVATE_ACCOUNT"}}
        }))
        self.paper.write_text("{}")
        self.archive.write_text(json.dumps(prices()))
        self.out.write_text(json.dumps(prior()))

    def run_build(self,now=None):
        return build("close",now or at(),self.feed,self.paper,self.out,self.archive)

    def test_nov17_official_archive_restored_on_nov18_delayed_job(self):
        out=self.run_build()
        self.assertEqual(out["status"],"ready")
        self.assertEqual(out["date"],"2026-11-17")
        self.assertEqual(out["source_date"],"2026-11-17")
        self.assertTrue(out["delayed_recovery"])
        self.assertIn("僅據官方收盤封存價",out["note"])
        self.assertIn("500 檔",out["note"])
        self.assertIn("非即時復盤",out["title"])
        self.assertNotIn("FABRICATED_INTRADAY_RISK",str(out))
        self.assertNotIn("NEVER_REUSE_PICK",str(out))
        self.assertNotIn("PRIVATE_ACCOUNT",str(out))
        self.assertNotIn("已驗證買點",str(out))
        self.assertEqual(out["us_market"],[])
        self.assertEqual(json.loads(self.out.read_text())["close"],out)
        self.assertEqual(json.loads(self.out.read_text())["checks"]["close"]["status"],"ready")

    def test_recovered_previous_date_never_eligible_for_new_day_line(self):
        recovered=self.run_build()
        ok,reason=can_send(recovered,"close",at(),"true","test-token","U"+"a"*32)
        self.assertFalse(ok)
        self.assertIn("日期",reason)
        self.assertEqual(recovered["date"],"2026-11-17")

    def test_no_previous_archive_fails_closed(self):
        self.archive.write_text(json.dumps(prices("2026-11-13")))
        out=self.run_build()
        self.assertEqual(out["status"],"pending")
        self.assertEqual(json.loads(self.out.read_text())["close"]["date"],"2026-11-13")

    def test_too_few_prices_and_invalid_types_fail_closed(self):
        for archive in [prices(count=499),{"schema":1,"kind":"price_fiction","days":prices()["days"]},
                        {"schema":1,"kind":"official_daily_close","days":{"2026-11-17":{}}}]:
            with self.subTest(archive=archive.get("kind")):
                self.archive.write_text(json.dumps(archive))
                self.out.write_text(json.dumps(prior()))
                got=self.run_build()
                self.assertEqual(got["status"],"pending")
                self.assertEqual(json.loads(self.out.read_text())["close"]["date"],"2026-11-13")

    def test_previous_report_same_or_newer_never_rewritten(self):
        doc=prior()
        doc["close"]["date"]="2026-11-17"
        self.out.write_text(json.dumps(doc))
        got=self.run_build()
        self.assertEqual(got["status"],"pending")
        self.assertEqual(json.loads(self.out.read_text())["close"]["date"],"2026-11-17")

    def test_after_1330_cannot_promote_previous_archive_as_current_close(self):
        for hour,minute in [(13,30),(14,0),(18,10),(23,59)]:
            with self.subTest(time=(hour,minute)):
                self.out.write_text(json.dumps(prior()))
                got=self.run_build(at(hour=hour,minute=minute))
                self.assertEqual(got["status"],"pending")
                self.assertEqual(json.loads(self.out.read_text())["close"]["date"],"2026-11-13")

    def test_missing_latest_previous_session_not_masked_by_older_archive(self):
        # The immediately previous session for Nov 19 is Nov 18. Do not
        # pretend a full Nov 17 archive satisfies it.
        got=self.run_build(at(day="2026-11-19",hour=8))
        self.assertEqual(got["status"],"pending")

    def test_same_day_verified_close_takes_precedence(self):
        self.feed.write_text(json.dumps({
            "data_date":"2026-11-18",
            "market":{"mode":"今日收盤","stale":False,
                      "close_count":500,"status":"已收盤"},
            "risk":{"score":50,"label":"正常"},
            "sectors":[],"attack":[]
        }))
        out=self.run_build(at(hour=18,minute=15))
        self.assertEqual(out["status"],"ready")
        self.assertEqual(out["date"],"2026-11-18")
        self.assertFalse(out.get("delayed_recovery",False))
        self.assertEqual(out["source_date"],"2026-11-18")

    def test_before_midnight_risk_not_falsely_claimed(self):
        out=self.run_build(at(day="2026-11-18",hour=0,minute=9))
        self.assertEqual(out["source_quality"],"archived_official_closes_only_not_independent_attestation")
        self.assertEqual(len(out["blocks"]),1)
        self.assertEqual(out["blocks"][0]["title"],"延遲補登說明")

    def test_archive_recovery_helper_does_not_modify_data(self):
        arch=prices()
        older=prior()["close"]
        before=json.dumps([arch,older],sort_keys=True)
        out=recover_previous_close_archive(at(),arch,older)
        self.assertEqual(out["date"],"2026-11-17")
        self.assertEqual(json.dumps([arch,older],sort_keys=True),before)


if __name__=="__main__":
    unittest.main()
