"""Forward-only pick validation: never invent winners from unavailable future closes."""
import copy
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from scripts.update_pick_validation import (
    GROUPS, HORIZONS, close_verified, freeze_picks, compile_report, update, net_percent
)

TZ=ZoneInfo("Asia/Taipei")
DATES=["2026-10-13","2026-10-14","2026-10-15","2026-10-16","2026-10-19",
       "2026-10-20","2026-10-21","2026-10-22","2026-10-23","2026-10-26"]
def archive(n=4):
    days={}
    for i,day in enumerate(DATES[:n]):
        days[day]={str(1000+k):100.0 for k in range(600)}
        days[day]["2344"]=[100,105,97,110,113,114,116,120,121,124][i]
        days[day]["2603"]=[90,92,90,91,96,99,102,105,107,110][i]
    return {"schema":1,"kind":"official_daily_close","days":days}

def feed(day="2026-10-13", stale=False):
    rows=[{"code":"2344","name":"合成測試股票", "score":95,"price":100},
          {"code":"2603","name":"合成測試股票二","score":90,"price":90}]
    return {"data_date":day,"updated_at":day+" 15:30",
            "market":{"mode":"今日收盤","stale":stale,"close_count":650},
            "holdings":{},"attack":rows,"monster":rows,
            "future_monster":rows,"next":rows,"tomorrow_monster":rows}

class PickValidationTests(unittest.TestCase):
    def test_freezes_original_five_groups_and_no_hindsight(self):
        a=archive()
        original=feed()
        result=freeze_picks(original,a["days"][DATES[0]],DATES[0])
        self.assertEqual(len(result),len(GROUPS)*2)
        self.assertEqual([p["code"] for p in result[:2]],["2344","2603"])
        self.assertEqual(result[0]["signal_close"],100)
        self.assertEqual(result[0]["rank"],1)
        self.assertEqual(result[-1]["group"],"future_monster")
        original["attack"][0]["price"]=150
        self.assertEqual(result[0]["signal_close"],100)
        self.assertFalse(any(p["signal_close"]==150 for p in result))
        self.assertLess(len(freeze_picks(original,a["days"][DATES[0]],DATES[0])),len(result),
                        "mismatched archive and ranking quote must be rejected")

    def test_matured_three_trading_days_and_longer_pending(self):
        a=archive(4)
        entries=freeze_picks(feed(),a["days"][DATES[0]],DATES[0])
        report=compile_report(entries,a,"2026-10-16 20:00")
        item=next(x for x in report["picks"] if x["group"]=="attack" and x["code"]=="2344")
        r3=item["outcomes"][0]
        self.assertEqual(r3["trading_days"],3)
        self.assertEqual(r3["status"],"complete")
        self.assertEqual(r3["end_day"],"2026-10-16")
        self.assertAlmostEqual(r3["gross_return_pct"],10.0)
        self.assertLess(r3["estimated_net_return_pct"],r3["gross_return_pct"])
        self.assertEqual(item["outcomes"][1]["status"],"pending")
        self.assertEqual(item["outcomes"][-1]["trading_days"],60)
        self.assertEqual(report["groups"]["attack"]["3"]["completed"],2)
        self.assertEqual(report["groups"]["attack"]["7"]["completed"],0)
        self.assertIsNone(report["groups"]["attack"]["7"]["win_rate_pct"])
        self.assertEqual(r3["expected_closes"],3)
        self.assertAlmostEqual(r3["worst_close_return_pct"],-3.0)

    def test_missing_stock_future_day_is_not_a_win(self):
        a=archive(4)
        a["days"][DATES[3]].pop("2344")
        item=freeze_picks(feed(),a["days"][DATES[0]],DATES[0])
        report=compile_report(item,a,"2026-10-16 20:00")
        attack=next(x for x in report["picks"] if x["group"]=="attack" and x["code"]=="2344")
        self.assertEqual(attack["outcomes"][0]["status"],"missing_price")
        self.assertEqual(report["groups"]["attack"]["3"]["missing_price"],1)
        self.assertEqual(report["groups"]["attack"]["3"]["completed"],1)
        self.assertIsNotNone(report["groups"]["attack"]["3"]["best_estimated_net_pct"],
                             "the unaffected pick is still a valid separate observation")

    def test_invalid_official_close_rejects_false_confidence(self):
        a=archive()
        f=feed()
        self.assertTrue(close_verified(f,a,DATES[0]))
        for bad in [
            {**f,"updated_at":DATES[0]+" 12:00"},
            {**f,"updated_at":DATES[1]+" 16:00"},
            {**f,"market":{**f["market"],"stale":True}},
            {**f,"market":{**f["market"],"close_count":True}},
            {**f,"market":{**f["market"],"mode":"盤中即時"}},
            {**f,"holdings":{"PRIVATE":{"cost":123456}}},
        ]:
            self.assertFalse(close_verified(bad,a,DATES[0]))

    def test_weekend_seed_and_duplicate_freeze(self):
        a=archive()
        f=feed("2026-10-16")
        f["attack"][0]["price"]=110;f["attack"][1]["price"]=91
        for group in GROUPS:f[group]=copy.deepcopy(f["attack"])
        old={"schema":1,"mode":"immutable_asof_pick_archive","picks":[]}
        now=datetime(2026,10,18,9,0,tzinfo=TZ)
        state,rep,captured=update(f,a,old,now)
        self.assertTrue(captured)
        self.assertTrue(state["picks"])
        self.assertEqual(state["picks"][0]["origin"],"verified_archive_bootstrap")
        self.assertEqual(rep["total_frozen_picks"],10)
        subsequent,report,again=update(f,a,state,now)
        self.assertFalse(again)
        self.assertEqual(subsequent,state)
        self.assertTrue(all(o["status"]=="pending" for p in report["picks"] for o in p["outcomes"]))

    def test_no_retroactive_seed_with_old_date_after_week(self):
        a=archive()
        f=feed("2026-10-16")
        for group in GROUPS:
            f[group]=[{"code":"2344","name":"測試","score":90,"price":110}]
        blank={"schema":1,"mode":"immutable_asof_pick_archive","picks":[]}
        state,_,captured=update(f,a,blank,datetime(2026,11,5,15,0,tzinfo=TZ))
        self.assertFalse(captured)
        self.assertFalse(state["picks"])

    def test_no_best_strategy_from_zero_matured_observations(self):
        a=archive(2)
        rows=freeze_picks(feed(),a["days"][DATES[0]],DATES[0])
        result=compile_report(rows,a,"2026-10-14 20:00")
        self.assertEqual(set(result["horizons_trading_days"]),set(HORIZONS))
        self.assertEqual(result["groups"]["monster"]["3"]["pending"],2)
        self.assertIsNone(result["groups"]["monster"]["3"]["win_rate_pct"])
        self.assertLess(net_percent(100,100),0,"fees and tax reduce even flat closes")

if __name__=="__main__":
    unittest.main()
