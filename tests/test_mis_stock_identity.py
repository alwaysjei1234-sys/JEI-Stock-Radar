"""MIS stock responses must match the requested ticker, market and channel."""
import copy
import unittest
from datetime import datetime
from unittest.mock import patch
from scripts import update_system as u


class MisStockIdentityTests(unittest.TestCase):
    now = datetime(2026, 11, 5, 10, 0, tzinfo=u.TZ)

    def quote(self, code='2330', **changes):
        return {'c':code, 'ex':'otc' if code=='6488' else 'tse', 'ch':code+'.tw',
                'd':'20261105', 't':'09:59:00', 'z':'105', 'y':'100', 'v':'20', **changes}

    def scan(self, messages, rows=None, retry=None):
        rows = copy.deepcopy(rows or [{'code':'2330','market':'TWSE','close':100}])
        calls=0
        def fetch(channels):
            nonlocal calls
            if channels==['tse_t00.tw']:return []
            calls+=1
            if calls==1:return []  # service availability probe
            return messages if calls==2 else retry or []
        with patch.object(u,'fetch_mis_channels',side_effect=fetch):
            return u.enrich_live(rows,self.now)

    def test_both_known_markets_accept_matching_identity(self):
        rows=[{'code':'2330','market':'TWSE','close':100}, {'code':'6488','market':'TPEX','close':100}]
        result,count,_,_,_=self.scan([self.quote(),self.quote('6488')],rows)
        self.assertEqual(count,2)
        self.assertTrue(all(row['live'] for row in result))

    def test_wrong_or_missing_market_channel_never_overwrites_official_close(self):
        for changes in ({'ex':'otc'},{'ch':'6488.tw'},{'ex':None},{'ch':None},{'ex':''},{'ch':'2330.tw|tse_6488.tw'}):
            with self.subTest(changes=changes):
                rows,count,_,_,stats=self.scan([self.quote(**changes)])
                self.assertEqual(count,0)
                self.assertEqual(rows[0],{'code':'2330','market':'TWSE','close':100})
                self.assertEqual(stats['rejected_identity'],1)

    def test_untrusted_quote_cannot_consume_the_bounded_retry_budget(self):
        by={'2330':{'market':'TWSE'}}
        for changes in ({'ex':'otc'},{'ch':'6488.tw'},{'ex':None}):
            with self.subTest(changes=changes):
                selected,_=u.select_mis_retry_channels([self.quote(z='-',**changes)],by,self.now,['2330'])
                self.assertEqual(selected,[])

    def test_retry_with_wrong_identity_cannot_recover_a_trade(self):
        rows,count,_,_,stats=self.scan([self.quote(z='-')],retry=[self.quote(ex='otc')])
        self.assertEqual(count,0)
        self.assertEqual(rows[0]['close'],100)
        self.assertEqual(stats['retry_requested'],1)
        self.assertEqual(stats['retry_recovered'],0)

    def test_malformed_messages_do_not_abort_a_valid_stock_response(self):
        rows,count,_,_,stats=self.scan([None,'invalid',1,self.quote()])
        self.assertEqual(count,1)
        self.assertEqual(rows[0]['close'],105)
        self.assertEqual(stats['malformed_messages'],3)

    def test_unknown_market_is_not_guessed_as_otc(self):
        rows,count,_,_,stats=self.scan([self.quote(ex='otc')],rows=[{'code':'2330','market':'UNKNOWN','close':100}])
        self.assertEqual(count,0)
        self.assertEqual(stats['requested_channels'],0)
        self.assertEqual(rows[0]['close'],100)


if __name__=='__main__':unittest.main()
