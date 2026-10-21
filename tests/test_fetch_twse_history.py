"""Offline tests for TWSE history fetch validation."""
import unittest
from unittest.mock import patch
import json
from scripts.fetch_twse_history import fetch_month

class FetchValidationTests(unittest.TestCase):
    def test_fetch_returns_ohlcv_and_legacy_prices(self):
        payload={"stat":"OK","title":"115年10月 2330 台積電 各日成交資訊",
          "fields":["日期","交易股數","成交金額","開盤價","最高價","最低價","收盤價"],
          "data":[["115/10/01","1,200","120,000","99","102","98","100"]]}
        class Response:
            status=200
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self,n): return json.dumps(payload).encode()
        with patch("scripts.fetch_twse_history.urllib.request.urlopen",return_value=Response()):
            result=fetch_month("2330","202610")
        self.assertEqual(result["prices"],[{"date":"2026-10-01","close":100.0}])
        self.assertEqual(result["ohlcv"],[{"date":"2026-10-01","open":99.0,"high":102.0,"low":98.0,"close":100.0,"volume":1200}])
        self.assertEqual(result["ohlcv_units"]["volume"],"shares")
        self.assertFalse(result["adjusted_for_corporate_actions"])
    def test_existing_legacy_file_is_not_silently_skipped(self):
        import tempfile
        from pathlib import Path
        from scripts.fetch_twse_history import main
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/"2330-202610.json"
            target.write_text(json.dumps({"code":"2330","prices":[]}),encoding="utf-8")
            with patch("sys.argv",["fetch_twse_history.py","--stock-code","2330",
                                   "--months","202610","--output-dir",directory]):
                with self.assertRaisesRegex(ValueError,"not validated OHLCV"):
                    main()
            self.assertEqual(json.loads(target.read_text())["prices"],[])
    def test_invalid_month(self):
        with self.assertRaises(ValueError):
            fetch_month("2330","202613")
    def test_invalid_code(self):
        with self.assertRaises(ValueError):
            fetch_month("ABC","202610")

if __name__=="__main__":
    unittest.main()
