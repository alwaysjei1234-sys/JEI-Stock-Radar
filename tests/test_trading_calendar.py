import unittest
from scripts.forward_pick_score import score_pick
from scripts.paper_report import build_report

class TradingCalendarTests(unittest.TestCase):
    def setUp(self):
        self.pick={"code":"2330","cohort":"monster","as_of":"2026-01-01"}
        self.calendar=["2026-01-02","2026-01-05","2026-01-06","2026-01-07","2026-01-08"]

    def test_missing_intermediate_price_does_not_shift_horizon(self):
        prices=[{"date":"2026-01-02","close":100},
                {"date":"2026-01-05","close":101},
                {"date":"2026-01-07","close":103},
                {"date":"2026-01-08","close":104}]
        result=score_pick(self.pick,prices,trading_dates=self.calendar)
        self.assertEqual(result["outcomes"]["3"]["exit_date"],"2026-01-07")
        self.assertEqual(result["outcomes"]["3"]["gross_return_pct"],3)

    def test_missing_exit_price_unavailable(self):
        prices=[{"date":"2026-01-02","close":100},
                {"date":"2026-01-05","close":101},
                {"date":"2026-01-06","close":102},
                {"date":"2026-01-08","close":104}]
        result=score_pick(self.pick,prices,trading_dates=self.calendar)
        self.assertEqual(result["outcomes"]["3"]["status"],"unavailable")

    def test_missing_entry_price_unavailable(self):
        result=score_pick(self.pick,[{"date":"2026-01-05","close":101}],trading_dates=self.calendar)
        self.assertEqual(result["outcomes"]["3"]["reason"],"missing_entry_close")

    def test_benchmark_calendar_passed_to_report(self):
        prices={"2330":[{"date":"2026-01-02","close":100},
                        {"date":"2026-01-05","close":101},
                        {"date":"2026-01-06","close":102},
                        {"date":"2026-01-08","close":104}]}
        benchmark=[{"date":d,"close":100} for d in self.calendar]
        report=build_report([self.pick],prices,benchmark)
        self.assertEqual(report["picks"][0]["outcomes"]["3"]["status"],"unavailable")
        self.assertEqual(report["cohort_summary"]["monster"]["3"]["matured"],0)

if __name__=="__main__":
    unittest.main()
