import unittest
from scripts.audit_paper_inputs import audit_snapshot_dates

class AuditTests(unittest.TestCase):
    def test_missing_future(self):
        result=audit_snapshot_dates([{"code":"2330","as_of":"2026-10-16"}],{})
        self.assertEqual(result["unresolved"],1)
    def test_future_present(self):
        result=audit_snapshot_dates([{"code":"2330","as_of":"2026-10-16"}],
                                    {"2330":[{"date":"2026-10-19","close":100}]})
        self.assertEqual(result["unresolved"],0)

if __name__=="__main__":
    unittest.main()
