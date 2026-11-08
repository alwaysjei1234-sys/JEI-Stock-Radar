import unittest
from tools.jei_ai_trader_modes import MODES, report_template, validate_report, load_profile

class FiveModeTests(unittest.TestCase):
    def test_all_five_modes(self):
        self.assertEqual(len(MODES), 5)
        for mode in MODES:
            template = report_template(mode)
            self.assertIn("as_of", template)
            self.assertIn("invalidating_conditions", template)
            self.assertFalse(not template["no_live_trade_signal"])
            self.assertTrue(validate_report(template))

    def test_no_unsupported_promotion(self):
        report = report_template("decision")
        report["no_live_trade_signal"] = False
        self.assertIn("trade_signal_not_allowed", validate_report(report))

    def test_profile(self):
        profile = load_profile()
        self.assertEqual(profile["market_priority"], ["TW", "US"])
        self.assertEqual(profile["risk_appetite"], "aggressive")
        self.assertFalse(profile["auto_trade"])

if __name__ == "__main__":
    unittest.main()
