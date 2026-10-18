import unittest
from scripts.paper_report import build_report

class BenchmarkDataSafetyTests(unittest.TestCase):
    def test_zero_benchmark_close_must_not_be_accepted(self):
        benchmark=[{"date":"2026-10-13","close":0},{"date":"2026-10-14","close":100}]
        with self.assertRaises(ValueError):
            build_report([],{},benchmark)

if __name__=="__main__":
    unittest.main()
