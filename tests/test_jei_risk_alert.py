import unittest
from tools.jei_risk_alert import evaluate

class RiskAlertTests(unittest.TestCase):
    def setUp(self):
        self.feed = {"data_date": "2026-11-06", "risk": {"level": "red", "score": 100, "reasons": ["加權指數 -4.51%"]}}

    def test_red_alert(self):
        self.assertIn("加權指數 -4.51%", evaluate(self.feed)["text"])

    def test_duplicate_suppression(self):
        self.assertIsNone(evaluate(self.feed, "2026-11-06:red:100"))

    def test_green_not_alert(self):
        self.feed["risk"]["level"] = "green"
        self.assertIsNone(evaluate(self.feed))

    def test_not_sent(self):
        self.assertEqual(evaluate(self.feed)["delivery_status"], "not_sent")

if __name__ == "__main__":
    unittest.main()
