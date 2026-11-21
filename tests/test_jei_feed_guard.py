import unittest
from tools.jei_feed_guard import parse_date, validate

class FeedGuardTests(unittest.TestCase):
    def test_roc_date(self):
        self.assertEqual(parse_date("1151106"), "2026-11-06")

    def test_valid_quote(self):
        rows = [{"Code": "2330", "Date": "1151106", "ClosingPrice": "100"}]
        self.assertEqual(validate(rows, "Code", "Date", "ClosingPrice")["valid_stocks"], 1)

    def test_empty(self):
        with self.assertRaises(ValueError):
            validate([], "Code", "Date", "ClosingPrice")

    def test_mixed_dates(self):
        rows = [
            {"Code": "2330", "Date": "1151106", "ClosingPrice": "100"},
            {"Code": "2317", "Date": "1151105", "ClosingPrice": "90"},
        ]
        with self.assertRaises(ValueError):
            validate(rows, "Code", "Date", "ClosingPrice")

if __name__ == "__main__":
    unittest.main()
