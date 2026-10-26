"""Regression: closure calendar and public holdings never leak private positions."""
import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from scripts.market_sessions import closure_reason, next_expected_session
from scripts.public_holding_signals import is_safe_public_holdings, build_public_holding_signals
from scripts.update_system import validated_previous_close

class MarketClosureAndPrivacyTests(unittest.TestCase):
    def test_typhoon_and_retrocession_closures(self):
        self.assertIn("颱風", closure_reason("2026-10-23"))
        self.assertIn("光復節", closure_reason("2026-10-26"))
        self.assertEqual(next_expected_session("2026-10-22"), "2026-10-27")
        self.assertEqual(next_expected_session("2026-10-26"), "2026-10-27")
        self.assertIsNone(closure_reason("2026-10-27"))

    def test_public_signal_privacy_allowlist(self):
        safe={"2330":{"score":65,"trend":"整理","action":"觀察","defense":100,"target":110,
                      "reason":"僅收盤技術面","as_of":"2026-10-22","status":"歷史參考"}}
        self.assertTrue(is_safe_public_holdings(safe))
        for secret in ("cost","shares","pnl","avg_cost","market_value"):
            self.assertFalse(is_safe_public_holdings({"2330":{**safe["2330"],secret:100}}))
        self.assertFalse(is_safe_public_holdings({"PRIVATE":{"cost":100}}))
        self.assertFalse(is_safe_public_holdings({"2330":{"score":True}}))

    def test_build_dated_signals_and_no_fake_prices(self):
        prices={f"2026-10-{i:02d}":{"2330":100+i} for i in range(15,23)}
        prior={"2330":{},"00937B":{"score":None,"trend":"資料不足","action":"觀察",
                                     "reason":"外部資料未驗證","as_of":"2026-10-22"}}
        # Remove null score: public schema only permits integer scores.
        prior["00937B"].pop("score")
        out=build_public_holding_signals(prior,prices,"2026-10-22",90)
        self.assertEqual(out["2330"]["as_of"],"2026-10-22")
        self.assertIn("defense",out["2330"])
        self.assertEqual(out["2330"]["action"],"防守觀察")
        self.assertEqual(out["00937B"],prior["00937B"])
        self.assertTrue(is_safe_public_holdings(out))
        self.assertNotIn("shares",str(out))
        self.assertNotIn("cost",str(out))

    def test_archived_close_accepts_safe_public_signals_only(self):
        feed={"data_date":"2026-10-22","updated_at":"2026-10-22 16:00",
              "market":{"mode":"今日收盤","stale":False,"close_count":1950},
              "holdings":{"2330":{"score":60,"trend":"整理","action":"觀察","as_of":"2026-10-22"}},
              "attack":[],"sectors":[]}
        now=datetime(2026,10,26,14,50,tzinfo=ZoneInfo("Asia/Taipei"))
        kept=validated_previous_close(feed,now)
        self.assertIsNotNone(kept)
        self.assertEqual(kept["data_date"],"2026-10-22")
        self.assertTrue(kept["market"]["historical_readonly"])
        feed["holdings"]["2330"]["cost"]=100
        self.assertIsNone(validated_previous_close(feed,now))

if __name__=="__main__":
    unittest.main()
