import unittest
from datetime import date
from scripts.backfill_twse_ohlcv import target_months

class BackfillCalendarTests(unittest.TestCase):
    def test_three_months_cross_year(self):
        self.assertEqual(target_months(date(2026,1,20)),['202511','202512','202601'])
    def test_three_months_regular(self):
        self.assertEqual(target_months(date(2026,10,20)),['202608','202609','202610'])

if __name__=='__main__':unittest.main()
