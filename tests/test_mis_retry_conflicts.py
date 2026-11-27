"""Retry batches must retain observations until canonical quote validation."""
import unittest
from datetime import datetime
from unittest.mock import patch
from scripts import update_system as u


class MisRetryConflictTests(unittest.TestCase):
    now=datetime(2026,11,27,10,0,tzinfo=u.TZ)
    def quote(self, **changes):
        return {**dict(c='2330',ex='tse',ch='2330.tw',d='20261127',
                      t='09:59:00',z='105',y='100',v='200'),**changes}
    def exercise(self, retried):
        rows=[{'code':'2330','market':'TWSE','close':100.,'pct':0.}]
        calls=[]
        def fetch(channels):
            calls.append(channels)
            if channels==['tse_t00.tw']:return []
            return [self.quote(z='-')] if len(calls)==1 else retried
        with patch.object(u,'mis_service_probe',return_value=(True,1,None)),patch.object(
                u,'fetch_mis_channels',side_effect=fetch):
            result=u.enrich_live(rows,self.now)
        self.assertEqual(calls,[['tse_2330.tw'],['tse_2330.tw'],['tse_t00.tw']])
        return result

    def test_retry_cannot_hide_conflicting_prices_or_previous_closes(self):
        for change in ({'z':'90'},{'y':'99'},{'t':'09:59:01'}):
            good=self.quote();other=self.quote(**change)
            for quotes in ([good,other],[other,good]):
                with self.subTest(change=change,first=quotes[0]):
                    rows,count,_,_,stats=self.exercise(quotes)
                    self.assertEqual(count,0)
                    self.assertEqual(rows,[{'code':'2330','market':'TWSE','close':100.,'pct':0.}])
                    self.assertEqual(stats.get('conflicting_symbols'),1)
                    self.assertEqual(stats['retry_recovered'],0)

    def test_stale_retry_duplicate_cannot_replace_a_valid_recovery(self):
        for bad in (self.quote(d='20261126'),self.quote(t='09:49:59'),
                    self.quote(y='0')):
            for quotes in ([self.quote(),bad],[bad,self.quote()]):
                with self.subTest(quotes=quotes):
                    rows,count,_,_,stats=self.exercise(quotes)
                    self.assertEqual((count,rows[0]['close']),(1,105.))
                    self.assertEqual(stats['retry_recovered'],1)

    def test_identical_flat_and_nested_retry_execution_still_recovers_once(self):
        flat=self.quote()
        nested=self.quote(z='-',t='09:59:40',trade={'t':'09:59:00','z':'105','v':1})
        rows,count,_,_,stats=self.exercise([flat,nested])
        self.assertEqual((count,rows[0]['close']),(1,105.))
        self.assertEqual(stats['retry_recovered'],1)
