import unittest
from scripts.collect_news_rss import classify_sectors, publication_utc

class NewsResearchTagTests(unittest.TestCase):
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
