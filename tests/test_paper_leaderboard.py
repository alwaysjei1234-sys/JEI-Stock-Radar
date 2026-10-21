import unittest
from scripts.paper_leaderboard import leaderboard

class LeaderboardTests(unittest.TestCase):
    def sample(self,verified):
        return {"data_quality":{"verified_by_system":verified},
                "cohort_summary":{"monster":{"3":{"matured":12,"pending_or_unavailable":2,
                                                 "win_rate_pct":75,"mean_net_return_pct":6,
                                                 "median_net_return_pct":4,"loss_rate_pct":25,"profit_factor":2.5}}},
                "benchmark_comparison":{"monster":{"3":{"paired_count":12,"mean_excess_pct":3}}}}
    def test_unverified_report_hides_returns(self):
        r=leaderboard(self.sample(False))
        self.assertFalse(r["verified"])
        monster=next(x for x in r["horizons"]["3"] if x["cohort"]=="monster")
        self.assertIsNone(monster["mean_net_return_pct"])
        self.assertIsNone(monster["win_rate_pct"])
        self.assertIsNone(monster["median_net_return_pct"])
        self.assertIsNone(monster["loss_rate_pct"])
        self.assertIsNone(monster["profit_factor"])
    def test_verified_report_exposes_stats(self):
        r=leaderboard(self.sample(True))
        monster=next(x for x in r["horizons"]["3"] if x["cohort"]=="monster")
        self.assertEqual(monster["mean_excess_pct"],3)
        self.assertEqual(monster["win_rate_pct"],75)
        self.assertEqual(monster["median_net_return_pct"],4)
        self.assertEqual(monster["loss_rate_pct"],25)
        self.assertEqual(monster["profit_factor"],2.5)
    def test_verified_but_small_sample_is_not_ranked(self):
        payload=self.sample(True)
        payload["cohort_summary"]["monster"]["3"]["matured"]=9
        payload["benchmark_comparison"]["monster"]["3"]["paired_count"]=9
        row=next(x for x in leaderboard(payload)["horizons"]["3"] if x["cohort"]=="monster")
        self.assertFalse(row["eligible"])
        self.assertIsNone(row["win_rate_pct"])
        self.assertIsNone(row["mean_excess_pct"])

    def test_all_five_horizons(self):
        self.assertEqual(set(leaderboard({})["horizons"]),{"3","7","15","30","60"})

if __name__=="__main__":
    unittest.main()
