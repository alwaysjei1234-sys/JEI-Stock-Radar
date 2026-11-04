import unittest
import json
import tempfile
from pathlib import Path

from scripts.update_system import attach_financial_context, load_recent_financial_snapshot


class FinancialContextTests(unittest.TestCase):
    SOURCES = {
        "twseRevenue": "https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
        "twseIncome": "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci",
        "twseBalance": "https://openapi.twse.com.tw/v1/opendata/t187ap07_L_ci",
    }

    def test_attaches_dated_official_financial_context_without_rescoring(self):
        row = {"code": "2330", "score": 91, "reason": "量價強勢", "cost": 500, "shares": 1000}
        snapshot = {
            "schemaVersion": 1,
            "generatedAt": "2026-11-04T12:50:00+00:00",
            "sources": self.SOURCES,
            "markets": {
                "listed": {
                    "2330": {
                        "revenue": {
                            "period": "2026-09-01", "publishedAt": "2026-10-17",
                            "monthlyYoYPct": 20.5, "monthlyMoMPct": -3.2,
                        },
                        "financials": {
                            "period": "2026-Q2", "publishedAt": "2026-10-30",
                            "eps": 13.25, "grossMarginPct": 55.4, "debtRatioPct": 40.1,
                        },
                    }
                }
            },
        }

        attach_financial_context([row], snapshot, "2026-11-04")

        self.assertEqual(row["score"], 91)
        self.assertEqual(row["financial_context"]["status"], "verified")
        self.assertIn("月營收 2026-09 公告 2026-10-17 YoY +20.5%／MoM -3.2%", row["reason"])
        self.assertIn("季報 2026-Q2 公告 2026-10-30 EPS 13.25、毛利率 55.4%、負債率 40.1%", row["reason"])
        self.assertIn("公告 2026-10-17", row["reason"])
        self.assertIn("不納入現行技術分數／回測", row["reason"])
        self.assertEqual(row["financial_context"]["sources"]["revenue"],self.SOURCES["twseRevenue"])
        self.assertEqual(row["financial_context"]["sources"]["income"],self.SOURCES["twseIncome"])
        self.assertEqual(row["financial_context"]["snapshot_generated_at"],snapshot["generatedAt"])
        self.assertEqual(row["financial_context"]["publication_dates"],
                         {"revenue":"2026-10-17","financials":"2026-10-30"})
        self.assertEqual(row["financial_context"]["availability"],None)
        self.assertEqual(row["cost"], 500)
        self.assertEqual(row["shares"], 1000)
        self.assertNotIn("cost", row["financial_context"])
        self.assertNotIn("shares", row["financial_context"])
        attach_financial_context([row], snapshot, "2026-11-04")
        self.assertEqual(row["reason"].count("月營收 2026-09"),1)

    def test_future_publication_is_not_used(self):
        row = {"code": "2330", "score": 85, "reason": "技術候選"}
        snapshot = {"schemaVersion": 1, "sources": self.SOURCES, "markets": {"listed": {"2330": {
            "revenue": {"period": "2026-10-01", "publishedAt": "2026-11-10", "monthlyYoYPct": 99},
            "financials": {"period": "2026-Q3", "publishedAt": "2026-11-12", "eps": 99},
        }}}}

        attach_financial_context([row], snapshot, "2026-11-05")

        self.assertEqual(row["score"], 85)
        self.assertEqual(row["financial_context"]["status"], "unverified")
        self.assertNotIn("99.0%", row["reason"])
        self.assertIn("財務資料未驗證", row["reason"])

    def test_future_reporting_period_is_not_used_even_if_date_looks_old(self):
        row={"code":"2330","score":85,"reason":"技術候選"}
        snapshot={"schemaVersion":1,"sources":self.SOURCES,"markets":{"listed":{"2330":{
            "revenue":{"period":"2026-12-01","publishedAt":"2026-10-17","monthlyYoYPct":99},
            "financials":{"period":"2026-Q4","publishedAt":"2026-10-30","eps":99},
        }}}}
        attach_financial_context([row],snapshot,"2026-11-04")
        self.assertEqual(row["financial_context"]["status"],"unverified")
        self.assertNotIn("99.0%",row["reason"])
        self.assertNotIn("EPS 99",row["reason"])

    def test_same_day_publication_is_excluded_without_intraday_publish_time(self):
        row={"code":"2330","score":85,"reason":"技術候選"}
        snapshot={"schemaVersion":1,"sources":self.SOURCES,"markets":{"listed":{"2330":{
            "revenue":{"period":"2026-10-01","publishedAt":"2026-11-04","monthlyYoYPct":22},
            "financials":{"period":"2026-Q3","publishedAt":"2026-11-04","eps":10},
        }}}}
        attach_financial_context([row],snapshot,"2026-11-04")
        self.assertEqual(row["financial_context"]["status"],"unverified")
        self.assertNotIn("22.0%",row["reason"])
        self.assertNotIn("EPS 10",row["reason"])

    def test_stale_and_malformed_financial_data_fail_closed(self):
        row = {"code": "2330", "score": 80, "reason": "候選"}
        snapshot = {"schemaVersion": 1, "sources": self.SOURCES, "markets": {"listed": {"2330": {
            "revenue": {"period": "2026-01-01", "publishedAt": "2026-02-01", "monthlyYoYPct": 10},
            "financials": {"period": "2025-Q4", "publishedAt": "2026-01-01", "eps": 10},
        }}}}

        attach_financial_context([row], snapshot, "2026-11-04")
        self.assertEqual(row["financial_context"]["status"], "unverified")
        self.assertNotIn("YoY", row["reason"])

        untouched = {"code": "2330", "score": 80, "reason": "候選"}
        attach_financial_context([untouched], {"schemaVersion": 2, "markets": {}}, "2026-11-04")
        self.assertNotIn("financial_context", untouched)

    def test_unknown_tickers_are_marked_without_changing_rank(self):
        row = {"code": "9999", "score": 88, "reason": "候選"}
        attach_financial_context([row], {"schemaVersion": 1, "markets": {"listed": {}, "otc": {}}}, "2026-11-04")
        self.assertEqual(row["score"], 88)
        self.assertEqual(row["financial_context"]["status"], "unverified")

    def test_snapshot_loader_rejects_stale_and_future_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"financial.json"
            for generated, expected in (("2026-11-04T12:00:00+00:00",True),
                                        ("2026-11-08T12:00:00+00:00",False),
                                        ("2026-10-01T12:00:00+00:00",False)):
                path.write_text(json.dumps({"schemaVersion":1,"generatedAt":generated,"markets":{}}))
                result=load_recent_financial_snapshot("2026-11-05",path)
                self.assertEqual(bool(result),expected,generated)

    def test_market_feed_workflow_runs_this_regression_before_updating(self):
        workflow=Path(__file__).resolve().parents[1]/".github/workflows/update-system.yml"
        source=workflow.read_text(encoding="utf-8")
        self.assertIn("tests/test_financial_context.py",source)
        self.assertIn("python -m unittest discover -s tests -p 'test_financial_context.py'",source)


if __name__ == "__main__":
    unittest.main()
