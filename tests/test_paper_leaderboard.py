import unittest
from scripts.paper_leaderboard import leaderboard

class LeaderboardTests(unittest.TestCase):
    def sample(self,verified):
        return {"data_quality":{"verified_by_system":verified},
                "cohort_summary":{"monster":{"3":{"matured":12,"pending_or_unavailable":2,
                                                 "win_rate_pct":75,"mean_net_return_pct":6}}},
                "benchmark_comparison":{"monster":{"3":{"paired_count":12,"mean_excess_pct":3}}}}
    def test_unverified_report_hides_returns(self):
        r=leaderboard(self.sample(False))
        self.assertFalse(r["verified"])
        monster=next(x for x in r["horizons"]["3"] if x["cohort"]=="monster")
        self.assertIsNone(monster["mean_net_return_pct"])
        self.assertIsNone(monster["win_rate_pct"])
    def test_verified_report_exposes_stats(self):
        r=leaderboard(self.sample(True))
        monster=next(x for x in r["horizons"]["3"] if x["cohort"]=="monster")
        self.assertEqual(monster["mean_excess_pct"],3)
        self.assertEqual(monster["win_rate_pct"],75)
    def test_all_five_horizons(self):
        self.assertEqual(set(leaderboard({})["horizons"]),{"3","7","15","30","60"})

if __name__=="__main__":
    unittest.main()
