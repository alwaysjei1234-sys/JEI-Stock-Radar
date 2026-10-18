import unittest
from scripts.export_feed_closes import extract_closes

class FeedCloseTests(unittest.TestCase):
    def test_prices_have_market_date_and_provenance(self):
        feed={"data_date":"2026-10-16","attack":[{"code":"2330","price":100}]}
        result=extract_closes(feed)
        self.assertEqual(result["prices"]["2330"]["date"],"2026-10-16")
        self.assertIn("official close not independently confirmed",result["source"])

    def test_conflicting_price_excluded(self):
        feed={"data_date":"2026-10-16","attack":[{"code":"2330","price":100}],
              "monster":[{"code":"2330","price":101}]}
        result=extract_closes(feed)
        self.assertNotIn("2330",result["prices"])
        self.assertEqual(result["conflict_codes"],["2330"])

    def test_ignore_target_price_and_invalid_values(self):
        feed={"data_date":"2026-10-16","attack":[{"code":"2330","target1":999},
             {"code":"2331","price":True},{"code":"2332","price":0}]}
        self.assertEqual(extract_closes(feed)["prices"],{})

if __name__=="__main__":
    unittest.main()
