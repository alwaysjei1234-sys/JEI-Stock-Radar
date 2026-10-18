import unittest
from scripts.paper_score_summary import summarize

class PaperSummaryTests(unittest.TestCase):
    def test_pending_not_counted_as_win(self):
        data = [
            {"cohort":"monster","outcomes":{"3":{"status":"mature","net_return_pct":10}}},
            {"cohort":"monster","outcomes":{"3":{"status":"mature","net_return_pct":-5}}},
            {"cohort":"monster","outcomes":{"3":{"status":"pending"}}},
        ]
        result=summarize(data)["monster"]["3"]
        self.assertEqual(result["total_signals"],3)
        self.assertEqual(result["matured"],2)
        self.assertEqual(result["pending_or_unavailable"],1)
        self.assertEqual(result["win_rate_pct"],50)
        self.assertEqual(result["mean_net_return_pct"],2.5)

    def test_empty_group_is_unknown_not_zero(self):
        row=summarize([])["pre_breakout"]["60"]
        self.assertIsNone(row["win_rate_pct"])
        self.assertIsNone(row["mean_net_return_pct"])

if __name__=="__main__":
    unittest.main()
