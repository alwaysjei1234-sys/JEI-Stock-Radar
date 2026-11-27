"""Recover incomplete past-month snapshots without inventing missing sessions."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.backfill_twse_ohlcv import run


class PastMonthGapTests(unittest.TestCase):
    def replay(self, replacement, error=False, complete_cache=False):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); cache=root/'candles';cache.mkdir()
            source=root/'system.json'
            source.write_text(json.dumps({'universe':[{'code':'2413','market':'TWSE'}],
                'patterns':{'status':'ready','data_date':'2026-11-27','signals':{
                'a':[{'code':'2413','close_series':[{'date':'2026-10-30','close':10},
                                                  {'date':'2026-11-27','close':11}]}]}}}))
            def payload(days):
                return {'code':'2413','market':'TWSE','adjusted_for_corporate_actions':False,
                        'ohlcv_units':{'volume':'shares'},'ohlcv':[{'date':d} for d in days]}
            for month,days in [('202609',['2026-09-30']),
                 ('202610',['2026-10-21','2026-10-30'] if complete_cache else ['2026-10-21']),
                 ('202611',['2026-11-27'])]:
                (cache/f'2413-{month}.json').write_text(json.dumps(payload(days)))
            path=cache/'2413-202610.json';before=path.read_bytes()
            with patch('scripts.backfill_twse_ohlcv.fetch_month',
                       side_effect=ValueError('official unavailable') if error else None,
                       return_value=payload(replacement)) as fetch, patch('scripts.backfill_twse_ohlcv.time.sleep'):
                count=run(source,cache,max_codes=1,pause=4)
            return count,fetch.call_args_list,before,path.read_bytes()

    def test_refresh_past_month_missing_an_observed_required_session(self):
        count,calls,before,after=self.replay(['2026-10-21','2026-10-30'])
        self.assertEqual(count,1)
        self.assertEqual([c.args for c in calls],[('2413','202610')])
        self.assertNotEqual(before,after)
        self.assertIn('2026-10-30',after.decode())

    def test_incomplete_response_preserves_original_bytes(self):
        count,calls,before,after=self.replay(['2026-10-21','2026-10-31'])
        self.assertEqual(len(calls),1)
        self.assertEqual(count,0)
        self.assertEqual(before,after)

    def test_transport_failure_preserves_original_bytes(self):
        count,calls,before,after=self.replay([],error=True)
        self.assertEqual(len(calls),1)
        self.assertEqual(count,0)
        self.assertEqual(before,after)

    def test_complete_past_month_cache_still_avoids_network(self):
        count,calls,before,after=self.replay([],complete_cache=True)
        self.assertEqual(count,0)
        self.assertEqual(calls,[])
        self.assertEqual(before,after)

if __name__=='__main__':unittest.main()
