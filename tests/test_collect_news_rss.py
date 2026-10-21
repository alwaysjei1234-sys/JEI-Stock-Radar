import unittest
from scripts.collect_news_rss import classify_sectors, publication_utc, headline_fingerprint, collect, sector_news_summary
from io import BytesIO

class NewsResearchTagTests(unittest.TestCase):
    def test_sector_summary_does_not_inflate_research_evidence(self):
        rows = [{"sectors":["光通訊/CPO"],"publisher_host":"news.example"},
                {"sectors":["光通訊/CPO"],"publisher_host":"news.example"},
                {"sectors":["光通訊/CPO"],"publisher_host":"another.example"}]
        result = sector_news_summary(rows)["光通訊/CPO"]
        self.assertEqual(result["headlines"],3)
        self.assertEqual(result["distinct_publisher_hosts"],2)
        self.assertEqual(result["research_institutions_verified"],0)

    def test_headline_deduplication_key(self):
        self.assertEqual(headline_fingerprint("CPO 產業！"), headline_fingerprint("cpo產業"))
        self.assertNotEqual(headline_fingerprint("CPO 產業"), headline_fingerprint("DRAM 產業"))

    def test_repeated_headlines_are_not_independent_sources(self):
        xml = b"""<rss><channel><item><title>CPO growth</title><link>https://example.com/a</link></item><item><title>CPO growth!</title><link>https://example.com/b</link></item></channel></rss>"""
        class Response(BytesIO):
            def __enter__(self): return self
            def __exit__(self, *args): self.close()
        result = collect(("tw_market",), opener=lambda *args, **kwargs: Response(xml))
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["independent_research_institutions"], 0)

    def test_multiple_sector_terms(self):
        self.assertIn("光通訊/CPO", classify_sectors("CPO 1.6T 光模組"))
        self.assertIn("記憶體/儲存", classify_sectors("HBM 需求增加"))
        self.assertEqual(classify_sectors("完全無關的新聞"), [])

    def test_utc_publication_date(self):
        self.assertEqual(publication_utc("Wed, 21 Oct 2026 01:19:54 GMT"),
                         "2026-10-21T01:19:54+00:00")
        self.assertIsNone(publication_utc("not a date"))
        self.assertIsNone(publication_utc(""))

if __name__ == "__main__":
    unittest.main()
