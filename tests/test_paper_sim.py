import unittest
from tools.paper_sim import Bar, Signal, simulate

class TestPaper(unittest.TestCase):
    def test_next_day_execution(self):
        b=[Bar('2026-01-01',100,100),Bar('2026-01-02',110,112),Bar('2026-01-03',120,125)]
        r=simulate(b,[Signal('2026-01-01','BUY'),Signal('2026-01-02','SELL')])
        self.assertEqual([x['date'] for x in r['trades']],['2026-01-02','2026-01-03'])
        self.assertEqual(r['ending_shares'],0)
    def test_reject_duplicate(self):
        with self.assertRaises(ValueError):
            simulate([Bar('2026-01-01',100,100)],[Signal('2026-01-01','BUY'),Signal('2026-01-01','SELL')])

if __name__=='__main__': unittest.main()
