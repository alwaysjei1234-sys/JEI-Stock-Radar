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

class OffhoursArchiveTests(unittest.TestCase):
    def test_weekend_preserves_original_close_and_never_claims_live(self):
        old=verified()
        after=MOD.validated_previous_close(old,SUNDAY)
        self.assertIsNotNone(after)
        self.assertEqual(after["data_date"],"2026-10-16")
        self.assertEqual(after["updated_at"],"2026-10-16 17:10")
        self.assertEqual(after["market"]["mode"],"今日收盤")
        self.assertTrue(after["market"]["historical_readonly"])
        self.assertEqual(after["market"]["last_checked_at"],"2026-10-18 07:29")
        self.assertEqual(len(after["attack"]),1)
        self.assertEqual(after["patterns"]["status"],"ready")
        self.assertNotIn("last_checked_at",old["market"],"old dict must not be mutated")
        next_session=MOD.validated_previous_close(after,datetime(2026,10,19,9,5,tzinfo=TAIPEI))
        self.assertTrue(next_session["market"]["historical_readonly"],"Monday research remains non-live")

    def test_reject_incomplete_stale_fake_private_or_expired_snapshots(self):
        base=verified()
        cases=[
            {**base,"data_date":"TWSE:1151016 / TPEx:1151016"},
            {**base,"data_date":"2026-10-18"},
            {**base,"updated_at":"2026-10-16 10:00"},
            {**base,"updated_at":"2026-10-18 17:10"},
            {**base,"market":{**base["market"],"stale":True}},
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
        self.assertTrue(market["updated_at"].startswith(market["data_date"]))
        self.assertFalse(market["market"]["stale"])
        self.assertGreaterEqual(market["market"]["close_count"],500)
        self.assertGreater(len(market["attack"]),0)
        self.assertGreater(len(market["sectors"]),0)
        self.assertEqual(market["holdings"],{})
        self.assertIsNotNone(MOD.validated_previous_close(market,datetime.fromisoformat(market["data_date"]+"T18:00:00").replace(tzinfo=TAIPEI)))

    def test_no_weekend_candle_in_published_history(self):
        history=json.loads((ROOT/"remote/history.json").read_text(encoding="utf-8"))
        self.assertFalse(any(x.get("date") in ("2026-10-17","2026-10-18") for x in history))
        self.assertLess(history[-1]["date"],"2026-10-21")
        self.assertLess(datetime.fromisoformat(history[-1]["date"]).weekday(),5)
        source=(ROOT/"scripts/update_system.py").read_text(encoding="utf-8")
        self.assertIn("if official_close_verified:",source)
        self.assertIn("history=update_history(history,date_key",source)
        self.assertLess(source.index("if official_close_verified:"),source.index("history=update_history(history,date_key"))
        self.assertIn("if retained is not None:",source)
        self.assertIn('"status":"archived_close_only"',source)

if __name__=="__main__":
    unittest.main()
