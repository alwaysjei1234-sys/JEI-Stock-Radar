from datetime import datetime
from pathlib import Path
from unittest import TestCase
from zoneinfo import ZoneInfo

from scripts.update_daily_news_watch import analyze_html


class DailyNewsWatchTests(TestCase):
    def test_extracts_topics_and_original_links_without_copying_editorial_text(self):
        fixture = Path(__file__).parent / "fixtures" / "daily_tw_news.html"
        result = analyze_html(fixture.read_text(encoding="utf-8"), datetime(2026, 10, 25, 9, 0, tzinfo=ZoneInfo("Asia/Taipei")))
        self.assertEqual(result["reportDate"], "2026-10-24")
        self.assertEqual(result["storyCount"], 3)
        topics = {item["id"]: item for item in result["themes"]}
        self.assertEqual(topics["us_semiconductors"]["articleCount"], 1)
        self.assertEqual(topics["taiwan_market_flow"]["references"][0]["url"], "https://example.com/tw-flow")
        self.assertNotIn("news-title", str(result))
        self.assertNotIn("費半與台積電 ADR 盤勢", str(result))
        self.assertTrue(result["interpretation"].startswith("JEI 自行"))

    def test_invalid_or_empty_page_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "no parseable"):
            analyze_html("<html><body>網站正在維護</body></html>")

    def test_untrusted_non_https_reference_falls_back_to_source_board(self):
        html = '<h2 id="focus">今日焦點</h2><div class="card"><div class="news-title"><span class="cat">美股</span>半導體</div><div class="news-body">費半</div></div>'
        result = analyze_html(html, datetime(2026, 10, 25, 9, 0, tzinfo=ZoneInfo("Asia/Taipei")))
        self.assertTrue(result["references"][0]["url"].startswith("https://daily-tw.up.railway.app/"))
