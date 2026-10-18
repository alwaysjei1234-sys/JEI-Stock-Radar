import unittest
from datetime import date, timedelta
from scripts.forward_pick_score import score_pick

class ForwardScoreTests(unittest.TestCase):
    def setUp(self):
        self.pick = {"code":"2330","cohort":"momentum","as_of":"2026-01-01"}
        self.sessions = [{"date":(date(2026,1,2)+timedelta(days=i)).isoformat(),"close":100+i} for i in range(65)]

    def test_mature_horizons(self):
        result=score_pick(self.pick,self.sessions)
        self.assertEqual(result["entry_price"],100)
        self.assertEqual(result["outcomes"]["3"]["status"],"mature")
        self.assertEqual(result["outcomes"]["3"]["gross_return_pct"],3)
        self.assertLess(result["outcomes"]["3"]["net_return_pct"],3)

    def test_no_future_leakage(self):
        result=score_pick(self.pick,self.sessions[:3])
        self.assertEqual(result["outcomes"]["3"]["status"],"pending")
        self.assertEqual(result["outcomes"]["60"]["status"],"pending")

    def test_reject_duplicates(self):
        with self.assertRaises(ValueError):
            score_pick(self.pick,self.sessions[:1]*2)

    def test_reject_invalid_price(self):
        with self.assertRaises(ValueError):
            score_pick(self.pick,[{"date":"2026-01-02","close":0}])

    def test_reject_unsorted(self):
        with self.assertRaises(ValueError):
            score_pick(self.pick,list(reversed(self.sessions[:2])))

    def test_no_entry(self):
        self.assertEqual(score_pick(self.pick,[])["outcomes"]["3"]["status"],"pending")

if __name__ == "__main__":
    unittest.main()
