import unittest
from scripts.paper_score_summary import summarize, rank_strategies

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
        self.assertEqual(result["median_net_return_pct"],2.5)
        self.assertEqual(result["max_net_return_pct"],10)
        self.assertEqual(result["min_net_return_pct"],-5)
        self.assertEqual(result["loss_rate_pct"],50)
        self.assertEqual(result["profit_factor"],2)
        self.assertEqual(result["profit_factor_note"],"measured")

    def test_no_losses_is_not_falsely_infinite_profit_factor(self):
        data = [{"cohort":"momentum","outcomes":{"3":{"status":"mature","net_return_pct":5}}}]
        result = summarize(data)["momentum"]["3"]
        self.assertIsNone(result["profit_factor"])
        self.assertEqual(result["profit_factor_note"],"no_realized_losses")

    def test_empty_group_is_unknown_not_zero(self):
        row=summarize([])["pre_breakout"]["60"]
        self.assertIsNone(row["win_rate_pct"])
        self.assertIsNone(row["mean_net_return_pct"])
        self.assertIsNone(row["median_net_return_pct"])
        self.assertIsNone(row["loss_rate_pct"])
        self.assertIsNone(row["profit_factor"])
        self.assertEqual(row["profit_factor_note"],"no_matured_samples")

class PaperRankingTests(unittest.TestCase):
    def test_minimum_sample_gate(self):
        data = [{"cohort":"monster","outcomes":{"15":{"status":"mature","net_return_pct":25}}}]
        rows = rank_strategies(data, horizon=15, min_matured=2)
        monster = next(r for r in rows if r["cohort"]=="monster")
        self.assertFalse(monster["eligible"])
        self.assertIsNone(monster["rank"])

    def test_median_beats_outlier_average(self):
        data = []
        for cohort, values in (("momentum",[1,2,3]),("monster",[-10,-9,100])):
            data.extend({"cohort":cohort,"outcomes":{"15":{"status":"mature","net_return_pct":v}}} for v in values)
        rows = rank_strategies(data, horizon=15, min_matured=3)
        self.assertEqual(rows[0]["cohort"],"momentum")
        self.assertEqual(rows[1]["cohort"],"monster")
        self.assertIsNone(rows[2]["rank"])

    def test_invalid_ranking_parameters(self):
        with self.assertRaises(ValueError): rank_strategies([],horizon=4)
        with self.assertRaises(ValueError): rank_strategies([],min_matured=0)

if __name__=="__main__":
    unittest.main()
