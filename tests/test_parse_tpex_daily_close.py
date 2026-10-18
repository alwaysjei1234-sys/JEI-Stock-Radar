import unittest
from scripts.parse_tpex_daily_close import parse_tpex_daily_close

class TpexParserTests(unittest.TestCase):
    def test_roc_and_missing_close(self):
        payload={"fields":["日期","收盤"],"aaData":[["115/10/15","101.5"],["115/10/16","--"]]}
        self.assertEqual(parse_tpex_daily_close(payload),[{"date":"2026-10-15","close":101.5}])
    def test_reject_missing_headers(self):
        with self.assertRaises(ValueError):
            parse_tpex_daily_close({"aaData":[["115/10/15","101"]]})
    def test_reject_duplicates(self):
        with self.assertRaises(ValueError):
            parse_tpex_daily_close({"fields":["日期","收盤"],"aaData":[["115/10/15","101"],["115/10/15","102"]]})

if __name__=="__main__":
    unittest.main()
