import unittest
from scripts.validated_paper_report import validate

class StrictObservationShapeTests(unittest.TestCase):
    def test_reject_non_object_benchmark_row(self):
        with self.assertRaises(ValueError):
            validate({"source":"test","prices":{},"benchmark":[None]})

    def test_reject_non_object_stock_row(self):
        with self.assertRaises(ValueError):
            validate({"source":"test",
                      "benchmark":[{"date":"2026-10-13","close":100}],
                      "prices":{"2330":[42]}})

if __name__=="__main__":
    unittest.main()
