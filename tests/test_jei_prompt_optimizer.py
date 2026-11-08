import unittest
from tools.jei_prompt_optimizer import build, diagnose

class PromptOptimizerTests(unittest.TestCase):
    def test_missing_constraints_flagged(self):
        result = build({"symbol": "2330"}, "decision")
        missing = {x["field"] for x in result["step2"]["diagnostics"]}
        self.assertIn("risk_limit", missing)
        self.assertIn("as_of", missing)
        self.assertEqual(result["step1"]["status"], "AWAITING_VERIFIED_MARKET_DATA")

    def test_complete_request(self):
        request = {key: "provided" for key in ("symbol", "market", "as_of", "horizon",
                   "strategy", "risk_limit", "benchmark", "data_sources", "backtest_window")}
        self.assertEqual(diagnose(request), [])
        self.assertIn("升級版", build(request)["step3"]["optimized_prompt"])

    def test_invalid_mode(self):
        with self.assertRaises(ValueError):
            build({}, "guaranteed_profit")

    def test_no_auto_trade(self):
        result = build({"symbol": "2317"})
        self.assertFalse(result["auto_trade"])
        self.assertFalse(result["auto_promote"])

if __name__ == "__main__":
    unittest.main()
