"""JEI official-close archive regression: keep non-trading days read-only and history clean."""
import importlib.util
import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("market_under_test",ROOT/"scripts/update_system.py")
MOD=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)
TAIPEI=ZoneInfo("Asia/Taipei")
FRIDAY=datetime(2026,10,16,17,10,tzinfo=TAIPEI)
SUNDAY=datetime(2026,10,18,7,29,tzinfo=TAIPEI)

def verified():
    return {
        "data_date":"2026-10-16","updated_at":"2026-10-16 17:10",
        "market":{"mode":"今日收盤","stale":False,"close_count":1954,"live_valid":False},
        "holdings":{},"attack":[{"code":"2330","score":88}],"sectors":[{"name":"記憶體"}],
        "patterns":{"status":"ready"},"risk":{"score":26,"label":"正常"}
    }

def market_latest_date(history):
    # The archive can advance on any verified trading day; never pin to yesterday.
    return max(x["date"] for x in history)

class OffhoursArchiveTests(unittest.TestCase):
    def test_weekend_preserves_original_close_and_never_claims_live(self):
        old=verified()
        after=MOD.validated_previous_close(old,SUNDAY)
        self.assertIsNotNone(after)
        self.assertEqual(after["data_date"],"2026-10-16")
        self.assertEqual(after["updated_at"],"2026-10-16 17:10")
        self.assertEqual(after["market"]["mode"],"今日收盤")
        self.assertTrue(after["market"]["historical_readonly"])
        self.assertTrue(after["market"]["stale"])
        self.assertEqual(after["market"]["last_checked_at"],"2026-10-18 07:29")
        self.assertEqual(len(after["attack"]),1)
        self.assertEqual(after["patterns"]["status"],"ready")
        self.assertNotIn("last_checked_at",old["market"],"old dict must not be mutated")
        next_session=MOD.validated_previous_close(after,datetime(2026,10,19,9,5,tzinfo=TAIPEI))
        self.assertTrue(next_session["market"]["historical_readonly"],"Monday research remains non-live")

    def test_archive_date_key_never_substitutes_today_for_stale_or_invalid_data(self):
        self.assertEqual(MOD.verified_archive_date("2026-10-27"),"2026-10-27")
        for invalid in ("TWSE:2026-10-28 / TPEx:2026-10-27","2026-10-32",
                        "2026-02-30","1151028","",None):
            with self.subTest(invalid=invalid):
                self.assertIsNone(MOD.verified_archive_date(invalid))
        source=(ROOT/"scripts/update_system.py").read_text(encoding="utf-8")
        self.assertIn("date_key=verified_archive_date(raw_date)",source)
        self.assertIn("date_key is not None and source_is_today",source)

    def test_newest_shared_official_close_advances_only_off_hours(self):
        self.assertEqual(MOD.latest_shared_close_date(
            {"2026-10-22"},{"2026-10-22"},"2026-10-25","2026-10-21",False,"2026-10-25"),"2026-10-22")
        self.assertIsNone(MOD.latest_shared_close_date(
            {"2026-10-22"},{"2026-10-22"},"2026-10-25","2026-10-22",False,"2026-10-25"))
        self.assertIsNone(MOD.latest_shared_close_date(
            {"2026-10-22"},{"2026-10-22"},"2026-10-25","2026-10-21",True,"2026-10-25"))
        self.assertEqual(MOD.normalize_exchange_date("115/10/22"),"2026-10-22")
        self.assertEqual(MOD.normalize_exchange_date("20261022"),"2026-10-22")

    def test_reject_incomplete_stale_fake_private_or_expired_snapshots(self):
        base=verified()
        cases=[
            {**base,"data_date":"TWSE:1151016 / TPEx:1151016"},
            {**base,"data_date":"2026-10-18"},
            {**base,"updated_at":"2026-10-16 10:00"},
            {**base,"updated_at":"2026-10-18 17:10"},
            {**base,"market":{**base["market"],"stale":True}},
            {**base,"market":{**base["market"],"stale":True,"historical_readonly":True},"updated_at":"2026-10-18 16:29"},
            {**base,"market":{**base["market"],"mode":"盤中即時"}},
            {**base,"market":{**base["market"],"close_count":499}},
            {**base,"market":{**base["market"],"close_count":True}},
            {**base,"holdings":{"PRIVATE":{"cost":1000,"shares":10}}},
            {**base,"attack":None},
            None
        ]
        for case in cases:
            with self.subTest(data=str(case)[:120]):
                self.assertIsNone(MOD.validated_previous_close(case,SUNDAY))
        self.assertIsNone(MOD.validated_previous_close(base,FRIDAY-timedelta(minutes=2)))
        self.assertIsNone(MOD.validated_previous_close(base,SUNDAY+timedelta(days=8)))

    def test_checked_in_market_snapshot_is_valid_nontrading_archive(self):
        market=json.loads((ROOT/"remote/system.json").read_text(encoding="utf-8"))
        self.assertRegex(market["data_date"],r"^\d{4}-\d{2}-\d{2}$")
        updated=datetime.strptime(market["updated_at"],"%Y-%m-%d %H:%M")
        data_day=datetime.strptime(market["data_date"],"%Y-%m-%d").date()
        self.assertGreaterEqual(updated.date(),data_day)
        self.assertGreaterEqual(market["market"]["close_count"],500)
        self.assertTrue(MOD.is_safe_public_holdings(market["holdings"]))
        self.assertTrue(all("cost" not in row and "shares" not in row and "pnl" not in row
                            for row in market["holdings"].values()))
        if market["market"]["mode"]=="資料過期":
            # A mixed-source feed is valid only as explicitly non-actionable
            # historical research; it must never mint today's stock picks.
            self.assertTrue(market["market"]["stale"])
            self.assertTrue(market["market"]["historical_readonly"])
            self.assertTrue(market["market"].get("no_new_picks"))
            self.assertEqual(market["attack"],[])
            self.assertEqual(market["next"],[])
            self.assertEqual(market["monster"],[])
            self.assertFalse(market["risk"].get("actionable",True))
            self.assertNotEqual(market["risk"]["level"],"green")
        else:
            self.assertEqual(market["market"]["historical_readonly"],updated.date()!=data_day)
            self.assertEqual(market["market"]["stale"],updated.date()!=data_day)
            self.assertGreater(len(market["attack"]),0)
            self.assertGreater(len(market["sectors"]),0)
            self.assertIsNotNone(MOD.validated_previous_close(
                market,datetime.strptime(market["updated_at"],"%Y-%m-%d %H:%M").replace(tzinfo=TAIPEI)+timedelta(minutes=1)))

    def test_no_weekend_candle_in_published_history(self):
        history=json.loads((ROOT/"remote/history.json").read_text(encoding="utf-8"))
        self.assertFalse(any(x.get("date") in ("2026-10-17","2026-10-18") for x in history))
        dates=[datetime.fromisoformat(row["date"]).date() for row in history]
        self.assertEqual(dates,sorted(set(dates)),"archive dates must be strictly increasing and unique")
        self.assertLessEqual(dates[-1],datetime.now(TAIPEI).date(),"archive cannot contain future candles")
        self.assertTrue(all(MOD.closure_reason(day) is None for day in dates),
                        "weekends, scheduled holidays and confirmed typhoon closures cannot have candles")
        self.assertTrue(all(len(row.get("prices") or {})>=500 for row in history),
                        "every archived day needs sufficient official price coverage")
        source=(ROOT/"scripts/update_system.py").read_text(encoding="utf-8")
        self.assertIn("if official_close_verified:",source)
        self.assertIn("history=update_history(history,date_key",source)
        self.assertLess(source.index("if official_close_verified:"),source.index("history=update_history(history,date_key"))
        self.assertIn("if retained is not None:",source)
        self.assertIn('"status":"archived_close_only"',source)

    def test_close_workflows_retry_in_archive_then_paper_order(self):
        archive=(ROOT/".github/workflows/archive-daily-picks.yml").read_text(encoding="utf-8")
        paper=(ROOT/".github/workflows/update-paper-performance.yml").read_text(encoding="utf-8")
        self.assertIn("- cron: '30 15 * * 1-5'",archive)
        self.assertIn("- cron: '50 15 * * 1-5'",paper)
        self.assertNotIn("- cron: '30 15 * * 1-5'",paper)

    def test_every_pick_snapshot_has_full_official_close_archive(self):
        snapshots=ROOT/"data/pick_snapshots"
        for path in sorted(snapshots.glob("????-??-??.json")):
            day=path.stem
            with self.subTest(day=day):
                snapshot=json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(snapshot.get("data_date"),day)
                if day == "2026-10-22":
                    self.assertEqual(snapshot.get("captured_at"),"2026-10-22 20:22")
                    self.assertEqual(snapshot.get("source_feed_commit"),"f40ced6e")
                self.assertTrue(all(p.get("as_of")==day for p in snapshot.get("picks",[])))
                close_path=ROOT/"data/feed_closes"/(day+".json")
                self.assertTrue(close_path.is_file(),f"missing close archive for {day}")
                archive=json.loads(close_path.read_text(encoding="utf-8"))
                self.assertEqual(archive.get("schema"),1)
                self.assertEqual(archive.get("kind"),"official_daily_close")
                self.assertEqual(archive.get("data_date"),day)
                self.assertIn(day,archive.get("days",{}))
                quotes=archive["days"][day]
                coverage=sum(isinstance(v,(int,float)) and not isinstance(v,bool) and v>0 for v in quotes.values())
                self.assertGreaterEqual(coverage,500)
                self.assertEqual(archive.get("coverage_count"),coverage)

if __name__=="__main__":
    unittest.main()
