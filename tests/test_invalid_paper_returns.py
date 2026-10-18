import unittest
from scripts.paper_score_summary import summarize

class InvalidReturnTests(unittest.TestCase):
    def test_nonfinite_returns_not_counted(self):
        picks=[{"cohort":"monster","outcomes":{"3":{"status":"mature","net_return_pct":v}}}
               for v in [float("nan"),float("inf"),True,4.0,-2.0]]
        result=summarize(picks)["monster"]["3"]
        self.assertEqual(result["total_signals"],5)
        self.assertEqual(result["matured"],2)
        self.assertEqual(result["pending_or_unavailable"],3)
        self.assertEqual(result["win_rate_pct"],50)
        self.assertEqual(result["mean_net_return_pct"],1)

if __name__=="__main__":
    unittest.main()
