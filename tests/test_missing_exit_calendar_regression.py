import unittest
from scripts.forward_pick_score import score_pick

class MissingExitRegression(unittest.TestCase):
    def test_missing_exit_price_cannot_be_replaced_by_next_quote(self):
        pick={"code":"2330","cohort":"monster","as_of":"2026-10-12"}
        dates=["2026-10-13","2026-10-14","2026-10-15","2026-10-16","2026-10-19"]
        rows=[{"date":day,"close":100+i} for i,day in enumerate(dates) if day!="2026-10-16"]
        result=score_pick(pick,rows,trading_dates=dates)
        self.assertEqual(result["outcomes"]["3"]["status"],"unavailable")
        self.assertEqual(result["outcomes"]["3"]["reason"],"missing_exit_close")
        self.assertEqual(result["outcomes"]["3"]["exit_date"],"2026-10-16")

if __name__=="__main__":
    unittest.main()
