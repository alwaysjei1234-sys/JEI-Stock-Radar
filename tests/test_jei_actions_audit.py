import unittest
from tools.jei_actions_audit import AREAS, build_report, inspect_feed

class AuditTests(unittest.TestCase):
    def test_missing_keys_and_bad_date(self):
        result = inspect_feed({'data_date': 'not-a-date'})
        self.assertIn('invalid_data_date', result['issues'])
        self.assertIn('missing:market', result['issues'])

    def test_red_risk_not_claim_delivery(self):
        feed = {'data_date':'2026-11-06', 'risk':{'level':'red','score':100}, 'market':{}}
        report = build_report(feed, 'abc')
        self.assertEqual(report['results']['line_delivery'], 'NOT_TESTED')
        self.assertIsNone(report['completion_percent'])
        self.assertEqual(report['source_commit'], 'abc')

    def test_working_31_labels(self):
        self.assertEqual(len(AREAS), 31)

if __name__ == '__main__':
    unittest.main()
