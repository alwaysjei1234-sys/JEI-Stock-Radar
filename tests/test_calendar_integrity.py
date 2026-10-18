import unittest
from scripts.forward_pick_score import score_pick

class CalendarIntegrityTests(unittest.TestCase):
    def test_reject_post_signal_price_outside_benchmark_calendar(self):
        pick={"code":"2330","cohort":"momentum","as_of":"2026-10-12"}
        rows=[{"date":"2026-10-13","close":100},
              {"date":"2026-10-14","close":101}]
        with self.assertRaises(ValueError):
            score_pick(pick,rows,trading_dates=["2026-10-13"])

if __name__=="__main__":
    unittest.main()
