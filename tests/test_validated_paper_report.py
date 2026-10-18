import unittest
from scripts.validated_paper_report import validate

class VerifiedInputTests(unittest.TestCase):
    def setUp(self):
        self.good={"source":"TWSE observed","prices":{"2330":[{"date":"2026-10-16","close":100}]},
                   "benchmark":[{"date":"2026-10-16","close":27000}]}
    def test_valid(self):
        self.assertEqual(validate(self.good)["source"],"TWSE observed")
    def test_requires_calendar(self):
        bad={**self.good}
        del bad["benchmark"]
        with self.assertRaises(ValueError):
            validate(bad)
    def test_reject_duplicate_date(self):
        bad={**self.good,"prices":{"2330":[{"date":"2026-10-16","close":100},
                                                {"date":"2026-10-16","close":101}]}}
        with self.assertRaises(ValueError):
            validate(bad)
    def test_reject_invalid_close(self):
        bad={**self.good,"benchmark":[{"date":"2026-10-16","close":float("nan")}]}
        with self.assertRaises(ValueError):
            validate(bad)
    def test_reject_missing_source(self):
        bad={**self.good,"source":""}
        with self.assertRaises(ValueError):
            validate(bad)

if __name__=="__main__":
    unittest.main()
