import unittest
from scripts.parse_twse_stock_day import parse_twse_stock_day, parse_twse_stock_day_ohlcv

class TwseParserTests(unittest.TestCase):
    def payload(self, rows):
        return {"stat":"OK","title":"115年10月 2330 台積電 各日成交資訊",
                "fields":["日期","交易股數","成交金額","開盤價","最高價","最低價","收盤價","漲跌價差","成交筆數"],
                "data":[[day,"1","1","100","100","100",price,"0","1"] for day,price in rows]}
    def test_roc_date_comma_price_and_suspension(self):
        p=self.payload([("115/10/01","1,050.00"),("115/10/02","--"),("115/10/05","1,060.00")])
        self.assertEqual(parse_twse_stock_day(p,"2330"),
                         [{"date":"2026-10-01","close":1050.0},{"date":"2026-10-05","close":1060.0}])
    def test_wrong_stock_rejected(self):
        with self.assertRaises(ValueError):
            parse_twse_stock_day(self.payload([("115/10/01","100")]),"2317")
    def test_duplicate_date_rejected(self):
        with self.assertRaises(ValueError):
            parse_twse_stock_day(self.payload([("115/10/01","100"),("115/10/01","101")]),"2330")
    def test_no_close_column_rejected(self):
        p=self.payload([("115/10/01","100")]);p["fields"][6]="最高價"
        with self.assertRaises(ValueError):
            parse_twse_stock_day(p,"2330")
    def test_valid_ohlcv_with_volume_shares(self):
        p=self.payload([("115/10/01","100")])
        p["data"][0]=["115/10/01","1,234","123,400","98","105","97","100","2","9"]
        self.assertEqual(parse_twse_stock_day_ohlcv(p,"2330"),
            [{"date":"2026-10-01","open":98.0,"high":105.0,"low":97.0,"close":100.0,"volume":1234}])
    def test_ohlcv_rejects_inconsistent_high_low(self):
        p=self.payload([("115/10/01","110")])
        with self.assertRaises(ValueError):
            parse_twse_stock_day_ohlcv(p,"2330")
    def test_ohlcv_rejects_fractional_volume(self):
        p=self.payload([("115/10/01","100")]);p["data"][0][1]="1.5"
        with self.assertRaises(ValueError):
            parse_twse_stock_day_ohlcv(p,"2330")
    def test_ohlcv_requires_explicit_volume_column(self):
        p=self.payload([("115/10/01","100")]);p["fields"][1]="未知股數"
        with self.assertRaises(ValueError):
            parse_twse_stock_day_ohlcv(p,"2330")
    def test_non_ok_rejected(self):
        p=self.payload([]);p["stat"]="很抱歉，沒有符合條件的資料"
        with self.assertRaises(ValueError):
            parse_twse_stock_day(p,"2330")

if __name__=="__main__":
    unittest.main()
