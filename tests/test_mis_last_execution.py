"""The exchange can publish an order-book update with its last execution nested."""
import copy
import unittest
from datetime import datetime
from unittest.mock import patch
from scripts import update_system as u

class MisLastExecutionTests(unittest.TestCase):
    now=datetime(2026,11,5,10,0,tzinfo=u.TZ)
    def quote(self,**changes):
        q=dict(c='2330',ex='tse',ch='2330.tw',d='20261105',t='09:59:55',z='-',y='2260',v='13374',
                    trade={'t':'09:59:25','v':1,'z':'2270','ft':20})
        q.update(changes);return q
    def scan(self,q):
        with patch.object(u,'fetch_mis_channels',return_value=[q]):
            return u.enrich_live([{'code':'2330','market':'TWSE','close':2260}],self.now)
    def test_nested_execution_restores_price_with_actual_trade_time(self):
        rows,count,_,_,_=self.scan(self.quote())
        self.assertEqual(count,1)
        self.assertEqual(rows[0]['close'],2270)
        self.assertEqual(rows[0]['quote_time'],'2026-11-05 09:59:25')
    def test_nested_execution_is_not_retried_as_missing(self):
        channels,_=u.select_mis_retry_channels([self.quote()],{'2330':{'market':'TWSE'}},self.now)
        self.assertEqual(channels,[])
    def test_stale_nested_trade_cannot_borrow_fresh_book_timestamp(self):
        rows,count,_,_,_=self.scan(self.quote(trade={'t':'09:40:00','z':'2270','v':1}))
        self.assertEqual(count,0);self.assertEqual(rows[0]['close'],2260)
    def test_bad_nested_executions_never_lift_coverage(self):
        for trade in [None,[],{}, {'t':'09:59:00','z':'NaN','v':1}, {'t':'09:59:00','z':'2270','v':0},
                      {'t':'10:02:00','z':'2270','v':1}, {'t':'09:59:56','z':'2270','v':1},
                      {'t':'08:59:00','z':'2270','v':1}, {'t':'09:59:00','z':'2270','v':1,'d':'20261104'}]:
            with self.subTest(trade=trade):self.assertEqual(self.scan(self.quote(trade=trade))[1],0)
    def test_top_level_executed_price_stays_authoritative(self):
        rows,count,_,_,_=self.scan(self.quote(z='2265'))
        self.assertEqual(count,1);self.assertEqual(rows[0]['close'],2265)
        self.assertEqual(rows[0]['quote_time'],'2026-11-05 09:59:55')
    def test_identity_and_parent_date_still_required(self):
        for changes in [{'ex':'otc'},{'ch':'6488.tw'},{'d':'20261104'},{'t':'bad'}]:
            with self.subTest(changes=changes):self.assertEqual(self.scan(self.quote(**changes))[1],0)
    def test_bid_ask_and_previous_close_still_cannot_fill_execution(self):
        self.assertIsNone(u.live_price(self.quote(trade={},a='2270_2280',b='2260_2250')))

if __name__=='__main__':unittest.main()
