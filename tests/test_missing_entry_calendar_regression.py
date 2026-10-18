import unittest
from scripts.forward_pick_score import score_pick

class MissingSessionRegression(unittest.TestCase):
    def test_missing_entry_on_calendar_never_uses_later_close(self):
        pick={"code":"2330","cohort":"momentum","as_of":"2026-10-12"}
        dates=["2026-10-13","2026-10-14","2026-10-15","2026-10-16"]
        rows=[{"date":day,"close":100} for day in dates[1:]]
        result=score_pick(pick,rows,trading_dates=dates)
        self.assertNotIn("entry_price",result)
        self.assertEqual(result["outcomes"]["3"]["reason"],"missing_entry_close")

if __name__=="__main__":
    unittest.main()
