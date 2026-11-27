"""Conflicting executed observations cannot be selected by response order."""
import copy
from datetime import datetime
import unittest
from unittest.mock import patch
from scripts import update_system as u


class MisStockConflictTests(unittest.TestCase):
    now = datetime(2026, 11, 27, 10, 0, tzinfo=u.TZ)
    def quote(self, **change):
        return dict(c='2330', ex='tse', ch='2330.tw', d='20261127',
                    t='09:59:00', z='105', y='100', **change)
    def run_quotes(self, quotes):
        original = [{'code':'2330','market':'TWSE','close':100.,'pct':0.}]
        rows = copy.deepcopy(original)
        with patch.object(u,'mis_service_probe',return_value=(True,1,None)), patch.object(
                u,'fetch_mis_channels',side_effect=lambda ch: [] if ch==['tse_t00.tw'] else quotes):
            result = u.enrich_live(rows, asof=self.now)
        return result, original

    def test_price_or_previous_close_conflict_rejects_both_orders(self):
        for key, value in (('z','90'),('y','99')):
            first=self.quote(); second={**first,key:value}
            for quotes in ([first,second],[second,first]):
                with self.subTest(key=key,reverse=quotes[0] is second):
                    (rows,count,_,_,stats),original=self.run_quotes(quotes)
                    self.assertEqual(count,0)
                    self.assertEqual(rows,original)
                    self.assertEqual(stats.get('conflicting_symbols'),1)

    def test_different_execution_times_are_not_arbitrarily_chosen(self):
        first=self.quote();second={**first,'t':'09:59:01'}
        for quotes in ([first,second],[second,first]):
            (rows,count,_,_,_),original=self.run_quotes(quotes)
            self.assertEqual((rows,count),(original,0))

    def test_flat_and_nested_same_execution_are_one_observation(self):
        flat=self.quote()
        nested={**flat,'z':'-','t':'09:59:40',
                'trade':{'t':'09:59:00','z':'105','v':1}}
        (rows,count,_,_,stats),_=self.run_quotes([flat,nested])
        self.assertEqual(count,1)
        self.assertEqual(rows[0]['close'],105.)
        self.assertEqual(stats['duplicate_messages'],1)

    def test_bad_identity_stale_or_invalid_price_cannot_poison_valid_quote(self):
        good=self.quote()
        for change in ({'ex':'otc'},{'d':'20261126'},{'t':'09:49:59'},
                       {'z':'NaN'},{'y':'0'},{'z':'-','b':'90_','a':'91_'}):
            bad={**good,**change}
            for quotes in ([bad,good],[good,bad]):
                with self.subTest(change=change):
                    (rows,count,_,_,_),_=self.run_quotes(quotes)
                    self.assertEqual((count,rows[0]['close']),(1,105.))

    def test_conflict_isolated_from_another_valid_stock(self):
        rows=[{'code':'2330','market':'TWSE','close':100.},
              {'code':'1101','market':'TWSE','close':50.}]
        good={**self.quote(),'c':'1101','ch':'1101.tw','z':'51','y':'50'}
        quotes=[self.quote(),{**self.quote(),'z':'90'},good]
        with patch.object(u,'mis_service_probe',return_value=(True,1,None)), patch.object(
                u,'fetch_mis_channels',side_effect=lambda ch: [] if ch==['tse_t00.tw'] else quotes):
            rows,count,_,_,_=u.enrich_live(rows,self.now)
        self.assertEqual(count,1)
        self.assertEqual([r.get('live',False) for r in rows],[False,True])
        self.assertEqual([r['close'] for r in rows],[100.,51.])
