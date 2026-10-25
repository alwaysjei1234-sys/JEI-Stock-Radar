import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "update_web_reco.py"
SPEC = importlib.util.spec_from_file_location("web_reco", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class PublicResearchSourceTests(unittest.TestCase):
    def test_public_report_requires_ticker_report_term_and_original_link(self):
        items = [
            {"title": "2330 台積電公開研究報告與目標價", "desc": "分析師摘要", "link": "https://example.com/report"},
            {"title": "台積電股價上漲", "desc": "市場新聞提及目標價", "link": "https://example.com/news"},
            {"title": "2330 台積電公開研究報告", "desc": "分享摘要", "link": "javascript:alert(1)"},
            {"title": "2330 台積電公開研究報告", "desc": "分析師摘要"},
            {"title": "2454 聯發科公開研究報告", "desc": "分析師摘要", "link": "https://example.com/other"},
        ]
        result = module.public_research_hits(items, "2330", "台積電")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["link"], "https://example.com/report")

    def test_plain_market_story_is_not_counted_as_a_research_report(self):
        items = [
            {"title": "2330 台積電今日成交量放大", "desc": "法人資金轉強", "link": "https://example.com/news"}
        ]
        self.assertEqual(module.public_research_hits(items, "2330", "台積電"), [])

    def test_recent_publicly_shared_broker_summary_is_linked_as_secondary_research(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime(2026, 10, 25, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        hits = module.public_shared_report_hits("3406", "玉晶光", now=now)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["evidence_level"], "publicly_shared_secondary")
        self.assertTrue(hits[0]["url"].startswith("https://vocus.cc/"))
        self.assertEqual(hits[0]["link"], hits[0]["url"])
        self.assertEqual(module.public_shared_report_hits(
            "3406", "玉晶光",
            now=datetime(2026, 12, 1, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))), [])
        self.assertEqual(module.public_shared_report_hits("2330", "台積電", now=now), [])


if __name__ == "__main__":
    unittest.main()
