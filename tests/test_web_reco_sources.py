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


if __name__ == "__main__":
    unittest.main()
