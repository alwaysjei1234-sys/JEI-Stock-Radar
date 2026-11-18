"""The same dated JEI strategy-quality evidence must reach brief and LINE.

No bot delivery/handset receipt is inferred; this tests bounded payload content
only, never sends a LINE message or touches an access token.
"""
import copy
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.build_daily_brief import generate
from scripts.send_line_brief import payload
from scripts.strategy_health import published_quality_brief_block

NOW=datetime(2026,11,17,18,10,tzinfo=ZoneInfo("Asia/Taipei"))
READER="U"+"a"*32


def data():
    return {
        "data_date":"2026-11-17",
        "market":{"mode":"今日收盤","stale":False,"close_count":1900,"status":"震盪"},
        "risk":{"score":88,"label":"紅燈防守","cash":"70%","reasons":["大盤偏弱"]},
        "sectors":[],
        "attack":[{"code":"3017","name":"奇鋐","score":95,"price":100,"change_pct":2}],
        "holdings":{"PERSONAL":{"secret":"DO_NOT_LEAK","cost":999999}},
        "strategy_health":{
            "source":"forward_official_close_pick_validation",
            "status":"ALL_OBSERVED_SHORT_HORIZONS_WEAK",
            "recommendation_mode":"research_only",
            "evaluated_windows":10,
            "underperforming_windows":10,
            "required_windows":10,
            "latest_official_day":"2026-11-16",
            "independent_oos_verified":False,
            "live_trading_verified":False,
        }
    }


class BriefLineStrategyHealthTests(unittest.TestCase):
    def ready(self, feed):
        return generate("close", NOW, feed, {},
                        us_fn=lambda n:[],global_fn=lambda n:[],news_fn=lambda n:[])

    def test_full_underperformance_is_explicit_first_class_brief_block(self):
        source=data()
        before=copy.deepcopy(source)
        report=self.ready(source)
        self.assertEqual(report["status"],"ready")
        blocks=[x for x in report["blocks"] if x.get("kind")=="strategy_quality"]
        self.assertEqual(len(blocks),1)
        self.assertEqual(blocks[0]["title"],"策略觀察績效警戒")
        self.assertIn("10組",blocks[0]["items"][0])
        self.assertIn("僅供模擬研究",blocks[0]["items"][1])
        self.assertNotIn("DO_NOT_LEAK",str(report))
        self.assertEqual(source,before)

    def test_line_payload_carries_warning_before_risk_and_picks(self):
        report=self.ready(data())
        body=payload(report,READER)["messages"][0]["text"]
        self.assertIn("策略觀察績效警戒",body)
        self.assertIn("新候選僅供模擬研究",body)
        self.assertLess(body.index("策略觀察績效警戒"),body.index("大盤風控"))
        self.assertLess(body.index("策略觀察績效警戒"),body.index("主攻候選"))
        self.assertNotIn("DO_NOT_LEAK",body)
        self.assertIn("僅研究參考",body)
        self.assertLessEqual(sum(2 if ord(c)>0xffff else 1 for c in body),5000)

    def test_missing_future_stale_and_spoofed_health_never_warn_as_all_weak(self):
        variants=[
            {},
            {"source":"not_the_official_pick_report"},
            {"latest_official_day":"2026-11-18"},
            {"latest_official_day":"2026-11-01"},
            {"latest_official_day":"2026-02-30"},
            {"required_windows":9},
            {"evaluated_windows":9},
            {"underperforming_windows":9},
            {"underperforming_windows":True},
            {"independent_oos_verified":True},
            {"live_trading_verified":True},
            {"recommendation_mode":"unverified"},
        ]
        for change in variants:
            with self.subTest(change=change):
                source=data()
                source["strategy_health"].update(change)
                if change=={}:
                    source.pop("strategy_health")
                report=self.ready(source)
                self.assertEqual(report["status"],"ready")
                self.assertFalse(any(x.get("kind")=="strategy_quality" for x in report["blocks"]))
                body=payload(report,READER)["messages"][0]["text"]
                self.assertNotIn("10組成熟觀察全部未達標",body)

    def test_partial_failure_is_not_falsely_described_as_all_ten(self):
        source=data()
        source["strategy_health"].update(
            status="SOME_OBSERVED_SHORT_HORIZONS_WEAK",
            recommendation_mode="review_before_using",
            underperforming_windows=3)
        report=self.ready(source)
        blocks=[x for x in report["blocks"] if x.get("kind")=="strategy_quality"]
        self.assertEqual(len(blocks),1)
        self.assertEqual(blocks[0]["title"],"策略觀察績效待核對")
        self.assertIn("3 組未達標",blocks[0]["items"][0])
        self.assertNotIn("全部未達標",str(report))

    def test_degraded_close_keeps_report_pending_not_sending_fake_candidates(self):
        feed=data()
        feed["market"]["stale"]=True
        report=self.ready(feed)
        self.assertEqual(report["status"],"pending")
        self.assertFalse(any(x.get("kind")=="strategy_quality" for x in report["blocks"]))
        self.assertNotIn("奇鋐",str(report))

    def test_no_unsupported_quality_when_health_gone(self):
        feed=data()
        feed.pop("strategy_health")
        self.assertIsNone(published_quality_brief_block(feed))
        report=self.ready(feed)
        self.assertEqual(report["status"],"ready")
        self.assertFalse(any(x.get("kind")=="strategy_quality" for x in report["blocks"]))


if __name__=="__main__":
    unittest.main()
