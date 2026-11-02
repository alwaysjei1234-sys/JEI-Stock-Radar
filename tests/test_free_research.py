import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "update_free_research.py"
SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "remote" / "free_research.json"
SPEC = importlib.util.spec_from_file_location("free_research", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class FreeResearchTests(unittest.TestCase):
    @unittest.skipUnless(SNAPSHOT_PATH.exists(), "snapshot is generated and strictly validated by update-free-research workflow")
    def test_published_snapshot_contains_only_public_normalized_records(self):
        payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(len(payload["sources"]), 10)
        self.assertGreater(len(payload["markets"]["listed"]), 1000)
        self.assertGreater(len(payload["markets"]["otc"]), 800)
        self.assertIn("revenue", payload["markets"]["listed"]["2330"])
        self.assertIn("financials", payload["markets"]["listed"]["2330"])
        self.assertIn("margin", payload["markets"]["otc"]["6488"])
        forbidden_keys = {"holdings", "shares", "cost", "pnl", "profit_loss"}
        def keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield str(key).lower()
                    yield from keys(child)
            elif isinstance(value, list):
                for child in value:
                    yield from keys(child)
        self.assertTrue(forbidden_keys.isdisjoint(set(keys(payload))))

    def test_roc_dates_and_numeric_values(self):
        self.assertEqual(module.roc_date("1151017"), "2026-10-17")
        self.assertIsNone(module.roc_date("1150230"))
        self.assertEqual(module.number("1,234.5%"), 1234.5)
        self.assertIsNone(module.number("--"))

    def test_official_rows_are_normalized_without_inventing_values(self):
        revenue = module.revenue_rows([{
            "出表日期": "1151017", "資料年月": "11509", "公司代號": "2330", "公司名稱": "台積電",
            "營業收入-當月營收": "357989000", "營業收入-去年同月增減(%)": "20.2",
            "累計營業收入-當月累計營收": "2800000000", "累計營業收入-前期比較增減(%)": "15.1",
        }])
        self.assertEqual(revenue["2330"]["period"], "2026-09-01")
        self.assertEqual(revenue["2330"]["monthlyYoYPct"], 20.2)
        self.assertIsNone(revenue["2330"]["monthlyMoMPct"])
        margin = module.tpex_margin_rows([{
            "Date": "1151022", "SecuritiesCompanyCode": "2330", "CompanyName": "台積電",
            "MarginPurchaseBalancePreviousDay": "10", "MarginPurchaseBalance": "13",
            "ShortSaleBalance": "2", "MarginPurchaseQuota": "100", "MarginPurchaseUtilizationRate": "13",
        }])
        self.assertEqual(margin["2330"]["marketDate"], "2026-10-22")
        self.assertEqual(margin["2330"]["marginBuyChange"], 3)
        self.assertEqual(margin["2330"]["marginUsagePct"], 13)

    def test_quarterly_financial_ratios_use_same_company_period(self):
        ratios = module.financial_rows([{
            "年度": "115", "季別": "2", "出表日期": "1151023", "公司代號": "2330", "公司名稱": "台積電",
            "營業收入": "1000", "營業毛利（毛損）淨額": "550", "營業利益（損失）": "400",
            "淨利（淨損）歸屬於母公司業主": "300", "基本每股盈餘（元）": "12.3",
        }], [{
            "年度": "115", "季別": "2", "出表日期": "1151023", "公司代號": "2330", "公司名稱": "台積電",
            "資產總計": "5000", "負債總計": "2000", "流動資產": "1500", "流動負債": "1000", "每股參考淨值": "88.8",
        }])["2330"]
        self.assertEqual(ratios["period"], "2026-Q2")
        self.assertEqual(ratios["publishedAt"], "2026-10-23")
        self.assertEqual(ratios["grossMarginPct"], 55)
        self.assertEqual(ratios["operatingMarginPct"], 40)
        self.assertEqual(ratios["parentNetMarginPct"], 30)
        self.assertEqual(ratios["debtRatioPct"], 40)
        self.assertEqual(ratios["currentRatioPct"], 150)
        self.assertEqual(ratios["eps"], 12.3)
        self.assertNotIn("2330", module.financial_rows([{"公司代號": "2330", "營業收入": "0"}], []))

    def test_financial_rows_do_not_mix_quarters(self):
        income = [{
            "年度": "115", "季別": "2", "出表日期": "1151023", "公司代號": "2330", "公司名稱": "台積電",
            "營業收入": "1000", "營業毛利（毛損）淨額": "550", "營業利益（損失）": "400",
            "淨利（淨損）歸屬於母公司業主": "300", "基本每股盈餘（元）": "12.3",
        }]
        older_balance = [{
            "年度": "115", "季別": "1", "出表日期": "1150701", "公司代號": "2330", "公司名稱": "台積電",
            "資產總計": "5000", "負債總計": "2000", "流動資產": "1500", "流動負債": "1000", "每股參考淨值": "88.8",
        }]
        record = module.financial_rows(income, older_balance)["2330"]
        self.assertEqual(record["period"], "2026-Q2")
        self.assertEqual(record["grossMarginPct"], 55)
        self.assertEqual(record["eps"], 12.3)
        self.assertIsNone(record["debtRatioPct"])
        self.assertIsNone(record["currentRatioPct"])
        self.assertIsNone(record["bookValuePerShare"])

    def test_snapshot_contains_both_markets_sources_and_only_public_data(self):
        fixtures = {
            module.SOURCES["twseRevenue"]: [{"公司代號": "2330", "公司名稱": "台積電", "資料年月": "11509", "出表日期": "1151017", "營業收入-去年同月增減(%)": "20"}],
            module.SOURCES["tpexRevenue"]: [{"公司代號": "6488", "公司名稱": "環球晶", "資料年月": "11509", "出表日期": "1151017"}],
            module.SOURCES["twseMargin"]: [{"股票代號": "2330", "股票名稱": "台積電", "融資今日餘額": "12", "融資前日餘額": "10", "融資限額": "100"}],
            module.SOURCES["tpexMargin"]: [{"Date": "1151022", "SecuritiesCompanyCode": "6488", "CompanyName": "環球晶", "MarginPurchaseBalance": "8", "MarginPurchaseBalancePreviousDay": "7", "MarginPurchaseQuota": "100"}],
            module.SOURCES["twseValuation"]: [{"Date": "1151022", "Code": "2330", "PEratio": "21", "DividendYield": "1.2", "PBratio": "4"}],
            module.SOURCES["tpexSbl"]: [{"Date": "1151022", "SecuritiesCompanyCode": "6488", "SecuritiesBorrowingBalanceOfTheMarketDay": "9"}],
            module.SOURCES["twseIncome"]: [{"年度": "115", "季別": "2", "出表日期": "1151023", "公司代號": "2330", "營業收入": "100", "營業毛利（毛損）淨額": "50"}],
            module.SOURCES["twseBalance"]: [{"年度": "115", "季別": "2", "出表日期": "1151023", "公司代號": "2330", "資產總計": "200", "負債總計": "100"}],
            module.SOURCES["tpexIncome"]: [{"Year": "115", "Season": "2", "Date": "1151023", "SecuritiesCompanyCode": "6488", "營業收入": "100", "營業毛利（毛損）淨額": "50"}],
            module.SOURCES["tpexBalance"]: [{"年度": "115", "季別": "2", "Date": "1151023", "SecuritiesCompanyCode": "6488", "資產總計": "200", "負債總計": "100"}],
        }
        payload = module.build_snapshot(fixtures.__getitem__, "2026-10-22", "2026-10-23T00:00:00+00:00")
        self.assertIn("2330", payload["markets"]["listed"])
        self.assertIn("6488", payload["markets"]["otc"])
        self.assertEqual(payload["markets"]["listed"]["2330"]["valuation"]["pe"], 21)
        self.assertEqual(payload["markets"]["listed"]["2330"]["financials"]["grossMarginPct"], 50)
        self.assertEqual(payload["markets"]["otc"]["6488"]["financials"]["debtRatioPct"], 50)
        self.assertEqual(payload["markets"]["otc"]["6488"]["margin"]["sblShortBalance"], 9)
        self.assertNotIn("holdings", json.dumps(payload).lower())
        self.assertEqual(len(payload["sources"]), 10)

    def cache_fixture(self):
        previous = {"schemaVersion": 1, "sources": module.SOURCES.copy(),
                    "generatedAt": "2026-10-30T12:00:00+00:00", "markets": {
                        "listed": {"2330": {"financials": {
                            "industryCoverage": "general_industry", "period": "2026-Q2",
                            "publishedAt": "2026-10-30", "eps": 49.33, "cost": "private"}}}, "otc": {}}}
        current = {"generatedAt": "2026-11-02T12:00:00+00:00", "markets": {
            "listed": {"2330": {"revenue": {"period": "2026-09-01"}}, "1232": {"financials": {"period": "2026-Q3", "eps": 8.03}}}, "otc": {}}}
        return current, previous

    def test_rolling_quarter_cache_preserves_dates_provenance_and_whitelist(self):
        current, previous = self.cache_fixture()
        result = module.retain_missing_financials(current, previous)
        record = result["markets"]["listed"]["2330"]["financials"]
        self.assertEqual(record["period"], "2026-Q2")
        self.assertEqual(record["publishedAt"], "2026-10-30")
        self.assertEqual(record["availability"], "retained_previous_snapshot")
        self.assertNotIn("cost", record)
        self.assertEqual(result["markets"]["listed"]["1232"]["financials"]["eps"], 8.03)
        self.assertEqual(result["financialCoverage"]["listed"]["retainedFinancialRecords"], 1)
        result.update(schemaVersion=1, sources=module.SOURCES.copy())
        next_snapshot, _ = self.cache_fixture()
        next_snapshot["generatedAt"] = "2026-11-03T12:00:00+00:00"
        again = module.retain_missing_financials(next_snapshot, result)
        self.assertEqual(again["markets"]["listed"]["2330"]["financials"]["cachedFromGeneratedAt"], previous["generatedAt"])

    def test_cache_rejects_unknown_source_and_future_snapshot(self):
        current, previous = self.cache_fixture()
        previous["sources"] = {}
        with self.assertRaises(ValueError):
            module.retain_missing_financials(current, previous)
        current, previous = self.cache_fixture()
        previous["generatedAt"] = "2026-11-03T00:00:00+00:00"
        with self.assertRaises(ValueError):
            module.retain_missing_financials(current, previous)

    def test_cache_does_not_merge_partial_new_quarter_or_add_removed_company(self):
        current, previous = self.cache_fixture()
        current["markets"]["listed"]["2330"]["financials"] = {"period": "2026-Q3", "eps": None}
        previous["markets"]["listed"]["9999"] = previous["markets"]["listed"]["2330"]
        module.retain_missing_financials(current, previous)
        self.assertIsNone(current["markets"]["listed"]["2330"]["financials"]["eps"])
        self.assertNotIn("9999", current["markets"]["listed"])

    def test_cache_skips_invalid_or_future_financial_values(self):
        for key, value in (("eps", float("nan")), ("eps", True), ("period", "2026-Q9"), ("period", "0000-Q1"), ("cachedFromGeneratedAt", "2026-10-30T12:00:00"), ("publishedAt", "2026-11-03")):
            current, previous = self.cache_fixture()
            previous["markets"]["listed"]["2330"]["financials"][key] = value
            module.retain_missing_financials(current, previous)
            self.assertNotIn("financials", current["markets"]["listed"]["2330"])

    def test_atomic_output_is_valid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "feed.json"
            module.write_atomic(path, {"safe": True})
            self.assertEqual(json.loads(path.read_text()), {"safe": True})


if __name__ == "__main__":
    unittest.main()
