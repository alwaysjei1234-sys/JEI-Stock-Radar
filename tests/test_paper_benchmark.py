import unittest
from scripts.paper_benchmark import compare_with_benchmark

class BenchmarkTests(unittest.TestCase):
    def test_same_window_excess(self):
        picks=[{"cohort":"monster","entry_date":"2026-01-02","outcomes":{"3":{"status":"mature","exit_date":"2026-01-07","net_return_pct":8.0}}},
               {"cohort":"monster","entry_date":"2026-01-02","outcomes":{"3":{"status":"mature","exit_date":"2026-01-07","net_return_pct":-2.0}}}]
        row=compare_with_benchmark(picks,{("2026-01-02","2026-01-07"):3.0})["monster"]["3"]
        self.assertEqual(row["paired_count"],2)
        self.assertEqual(row["mean_excess_pct"],0)
        self.assertEqual(row["benchmark_beat_rate_pct"],50)

    def test_missing_benchmark_not_zero(self):
        picks=[{"cohort":"momentum","entry_date":"2026-01-02","outcomes":{"7":{"status":"mature","exit_date":"2026-01-13","net_return_pct":10}}}]
        row=compare_with_benchmark(picks,{})["momentum"]["7"]
        self.assertEqual(row["paired_count"],0)
        self.assertEqual(row["missing_benchmark_count"],1)
        self.assertIsNone(row["mean_excess_pct"])

if __name__=="__main__":
    unittest.main()
