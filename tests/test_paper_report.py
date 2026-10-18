import unittest
from scripts.paper_report import build_report

class ReportTests(unittest.TestCase):
    def test_full_report_and_benchmark(self):
        picks=[{"code":"2330","cohort":"momentum","as_of":"2026-01-01"}]
        prices={"2330":[{"date":f"2026-01-{d:02d}","close":100+d-2} for d in range(2,9)]}
        benchmark=[{"date":f"2026-01-{d:02d}","close":100} for d in range(2,9)]
        report=build_report(picks,prices,benchmark)
        self.assertEqual(report["sample_count"],1)
        self.assertEqual(report["cohort_summary"]["momentum"]["3"]["matured"],1)
        self.assertEqual(report["benchmark_comparison"]["momentum"]["3"]["paired_count"],1)
        self.assertEqual(report["cohort_summary"]["momentum"]["60"]["pending_or_unavailable"],1)

    def test_duplicate_pick_rejected(self):
        pick={"code":"2330","cohort":"monster","as_of":"2026-01-01"}
        with self.assertRaises(ValueError):
            build_report([pick,pick],{})

    def test_no_prices_not_fabricated(self):
        pick={"code":"2330","cohort":"pre_breakout","as_of":"2026-01-01"}
        report=build_report([pick],{})
        self.assertEqual(report["cohort_summary"]["pre_breakout"]["3"]["matured"],0)
        self.assertIsNone(report["cohort_summary"]["pre_breakout"]["3"]["win_rate_pct"])

if __name__=="__main__":
    unittest.main()
