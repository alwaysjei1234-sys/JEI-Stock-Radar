"""Do not relabel an older TWSE response with the date in the request URL."""
import unittest
from unittest.mock import patch
from scripts import update_system as feed


def stock_response():
    return {'stat':'OK','date':'20261103','tables':[{
        'fields':['證券代號','證券名稱','收盤價','漲跌價差','漲跌(+/-)','成交股數'],
        'data':[['2330','台積電','100','2','-','1000']]}]}


class TwseStockResponseDateTests(unittest.TestCase):
    def test_matching_exchange_response_keeps_its_validated_date(self):
        with patch.object(feed,'fetch_json',return_value=stock_response()):
            rows=feed.fetch_twse_daily('20261103')
        self.assertEqual((rows[0]['date'],rows[0]['close'],rows[0]['change']),('20261103',100,-2))

    def test_old_missing_future_or_invalid_response_date_cannot_be_relabelled(self):
        for date in ('20261102',None,'20261104','20260230'):
            raw=stock_response();raw['date']=date
            with self.subTest(date=date),patch.object(feed,'fetch_json',return_value=raw):
                with self.assertRaises(ValueError):feed.fetch_twse_daily('20261103')

    def test_non_ok_response_with_leftover_table_is_not_accepted(self):
        raw=stock_response();raw['stat']='沒有符合條件的資料'
        with patch.object(feed,'fetch_json',return_value=raw):
            with self.assertRaises(ValueError):feed.fetch_twse_daily('20261103')

    def test_invalid_requested_session_never_accepts_a_table(self):
        for date in ('20260230','date=20261103',None,20261103):
            with self.subTest(date=date),patch.object(feed,'fetch_json',return_value=stock_response()):
                with self.assertRaises(ValueError):feed.fetch_twse_daily(date)


class TwseIndexResponseDateTests(unittest.TestCase):
    def daily(self):
        return {'date':'20261103','stat':'OK','tables':[{
            'fields':['指數','漲跌百分比(%)','漲跌(+/-)'],
            'data':[['其他指數','9','+'],['發行量加權股價指數','3.59',"<p style='color:green'>-</p>"]]}]}

    def openapi(self,date='1151103',pct='3.59'):
        return {'日期':date,'指數':'發行量加權股價指數','漲跌百分比':pct,'漲跌':'-'}

    def test_same_day_daily_index_uses_named_columns_and_sign(self):
        self.assertEqual(feed.twse_daily_index_pct(self.daily(),'20261103'),-3.59)

    def test_cached_daily_index_cannot_be_used_for_today(self):
        raw=self.daily();raw['date']='20261102'
        with self.assertRaises(ValueError):feed.twse_daily_index_pct(raw,'20261103')
        raw=self.daily();raw['stat']='沒有符合條件的資料'
        with self.assertRaises(ValueError):feed.twse_daily_index_pct(raw,'20261103')

    def test_openapi_uses_only_matching_session_even_if_old_row_is_first(self):
        rows=[self.openapi('1151102','0.65'),self.openapi()]
        self.assertEqual(feed.twse_openapi_index_pct(rows,'2026-11-03'),-3.59)
        self.assertIsNone(feed.twse_openapi_index_pct(rows[:1],'2026-11-03'))

    def test_missing_invalid_and_wrong_index_rows_are_never_substitutes(self):
        for date in (None,'','1151102','1150230','20261104'):
            with self.subTest(date=date):
                self.assertIsNone(feed.twse_openapi_index_pct([self.openapi(date)],'2026-11-03'))
        wrong=self.openapi();wrong['指數']='寶島股價指數'
        self.assertIsNone(feed.twse_openapi_index_pct([wrong],'2026-11-03'))
        for pct in (None,'--','NaN','Infinity',True):
            self.assertIsNone(feed.twse_openapi_index_pct([self.openapi(pct=pct)],'2026-11-03'))

    def test_valid_zero_change_is_not_missing(self):
        self.assertEqual(feed.twse_openapi_index_pct([self.openapi(pct='0')],'2026-11-03'),0)
        raw=self.daily();raw['tables'][0]['data'][1][1]='0'
        self.assertEqual(feed.twse_daily_index_pct(raw,'20261103'),0)
