import unittest
import json
import tempfile
import urllib.parse
import unittest.mock
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from scripts import build_daily_brief as b
from scripts import send_line_brief as line

CLOSE=datetime(2026,10,16,18,10,tzinfo=ZoneInfo("Asia/Taipei"))
FEED={"data_date":"2026-10-16",
      "market":{"mode":"今日收盤","stale":False,"close_count":1700,"status":"震盪"},
      "risk":{"score":26,"label":"正常","cash":"20%~30%","reasons":["加權 +0.30%"]},
      "sectors":[{"name":"記憶體","score":79,"avg_pct":2.74,"leaders":[{"name":"華邦電"}]}],
      "attack":[{"code":"2344","name":"華邦電","score":90,"price":58,"change_pct":3.0}],
      "holdings":{"PERSONAL":{"name":"NEVER_PUBLIC","cost":9999}}}
PAPER={"last_processed_day":"2026-10-16","capital_per_strategy":1000000,
       "strategies":{"fixed5":{"name":"固定 +5%","summary":{"estimated_liquidation_equity_ntd":970000}}}}

class BriefTests(unittest.TestCase):
    def test_ready_close_has_no_private_data(self):
        report=b.generate("close",CLOSE,FEED,PAPER)
        self.assertEqual(report["status"],"ready")
        self.assertIn("記憶體",str(report))
        self.assertIn("固定 +5%",str(report))
        self.assertNotIn("NEVER_PUBLIC",str(report))

    def test_close_stale_or_previous_day_fails_closed(self):
        feed=dict(FEED,data_date="2026-10-15")
        self.assertEqual(b.generate("close",CLOSE,feed,PAPER)["status"],"pending")
        feed=dict(FEED,market=dict(FEED["market"],stale=True))
        self.assertEqual(b.generate("close",CLOSE,feed,PAPER)["status"],"pending")
        feed=dict(FEED,market=dict(FEED["market"],close_count=2))
        self.assertEqual(b.generate("close",CLOSE,feed,PAPER)["status"],"pending")

    def test_morning_must_use_previous_close(self):
        at=CLOSE.replace(hour=8)
        self.assertEqual(b.generate("morning",at,FEED,PAPER)["status"],"pending")
        feed=dict(FEED,data_date="2026-10-15")
        report=b.generate("morning",at,feed,PAPER,us_fn=lambda n: [],global_fn=lambda n: [],news_fn=lambda n: [])
        self.assertEqual(report["status"],"ready")
        self.assertIn("暫無可信來源",str(report))
        self.assertNotIn("NEVER_PUBLIC",str(report))

    def test_cross_market_quotes_use_exchange_timezone_and_keep_dates(self):
        now=datetime(2026,10,25,10,0,tzinfo=ZoneInfo("Asia/Taipei"))
        responses={}
        for code,tz,stamps in [
            ("^SOX","America/New_York",[datetime(2026,10,22,20,tzinfo=ZoneInfo("UTC")).timestamp(),datetime(2026,10,23,20,tzinfo=ZoneInfo("UTC")).timestamp()]),
            ("^N225","Asia/Tokyo",[datetime(2026,10,22,6,tzinfo=ZoneInfo("UTC")).timestamp(),datetime(2026,10,23,6,tzinfo=ZoneInfo("UTC")).timestamp()])
        ]:
            responses[code]={"chart":{"result":[{"meta":{"exchangeTimezoneName":tz},"timestamp":stamps,"indicators":{"quote":[{"close":[100,101]}]}}],"error":None}}
        def fake_get_url(url):
            for code,payload in responses.items():
                if urllib.parse.quote(code,safe="") in url: return json.dumps(payload)
            raise OSError("symbol unavailable")
        with unittest.mock.patch.object(b,"get_url",side_effect=fake_get_url):
            quotes=b.fetch_market_symbols((("^SOX","費城半導體"),("^N225","日經 225"),("^BAD","無效")),now)
        self.assertEqual([(x["name"],x["date"]) for x in quotes],[("費城半導體","2026-10-23"),("日經 225","2026-10-23")])
        self.assertTrue(all(x["source"]=="Yahoo Finance" for x in quotes))

    def test_morning_separates_core_us_and_cross_market_quotes(self):
        at=datetime(2026,10,24,9,0,tzinfo=ZoneInfo("Asia/Taipei"))
        feed=dict(FEED,data_date="2026-10-23")
        global_quotes=[{"name":"費城半導體","date":"2026-10-23","close":10779.46,"change_pct":0.44,"source":"Yahoo Finance"}]
        report=b.generate("morning",at,feed,PAPER,us_fn=lambda n: [],global_fn=lambda n: global_quotes,news_fn=lambda n: [])
        self.assertEqual(report["global_market"],global_quotes)
        self.assertIn("跨市場風險指標",str(report["blocks"]))
        self.assertIn("市場日 2026-10-23",str(report["blocks"]))

    def test_line_is_explicitly_opt_in(self):
        report=b.generate("close",CLOSE,FEED,PAPER)
        user="U"+"a"*32
        self.assertFalse(line.can_send(report,"close",CLOSE,"","token",user)[0])
        self.assertFalse(line.can_send(report,"close",CLOSE,"true","",user)[0])
        self.assertFalse(line.can_send(report,"morning",CLOSE,"true","token",user)[0])
        self.assertTrue(line.can_send(report,"close",CLOSE,"true","token",user)[0])
        self.assertNotIn("NEVER_PUBLIC",str(line.payload(report,user)))

    def test_weekend_preserves_last_verified_close(self):
        saturday=datetime(2026,10,17,18,20,tzinfo=ZoneInfo("Asia/Taipei"))
        friday=b.generate("close",CLOSE,FEED,PAPER)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            feed_path=root/"system.json"
            paper_path=root/"paper.json"
            output=root/"brief.json"
            feed_path.write_text(json.dumps(FEED,ensure_ascii=False),encoding="utf-8")
            paper_path.write_text(json.dumps(PAPER,ensure_ascii=False),encoding="utf-8")
            output.write_text(json.dumps({"schema":1,"morning":None,"close":friday},ensure_ascii=False),encoding="utf-8")
            checked=b.build("close",saturday,feed_path,paper_path,output)
            saved=json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(checked["status"],"pending")
            self.assertEqual(saved["close"]["date"],"2026-10-16")
            self.assertEqual(saved["close"]["status"],"ready")
            self.assertEqual(saved["checks"]["close"]["date"],"2026-10-17")
            self.assertEqual(saved["checks"]["close"]["status"],"pending")

    def test_quota_only_free_plan(self):
        real=line.api_get
        try:
            line.api_get=lambda url,t: {"type":"limited","value":200} if url.endswith("/quota") else {"totalUsage":54}
            self.assertTrue(line.quota_ok("token",55))
            self.assertFalse(line.quota_ok("token",54))
            line.api_get=lambda url,t: {"type":"limited","value":3000} if url.endswith("/quota") else {"totalUsage":0}
            self.assertFalse(line.quota_ok("token"))
        finally:
            line.api_get=real

if __name__=="__main__": unittest.main()
