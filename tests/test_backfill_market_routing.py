"""Keep the bounded TWSE request budget on same-snapshot listed symbols."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.backfill_twse_ohlcv import run


class BackfillMarketRoutingTests(unittest.TestCase):
    def replay(self, universe, codes, max_codes=12):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source=root/'system.json'
            source.write_text(json.dumps({'universe':universe,'patterns':{
                'status':'ready','data_date':'2026-11-27',
                'signals':{'breakout':[{'code':c} for c in codes]}}}))
            def fetched(code, month):
                return {'code':code,'market':'TWSE','ohlcv':[{'date':'2026-11-27'}]}
            with patch('scripts.backfill_twse_ohlcv.fetch_month',side_effect=fetched) as fetch, patch('scripts.backfill_twse_ohlcv.time.sleep'):
                count=run(source,root/'candles',max_codes=max_codes,pause=4)
            return count,[call.args for call in fetch.call_args_list]

    def test_observed_mixed_market_watchlist_never_routes_tpex_to_twse(self):
        codes=['1464','5457','3310','6908','6190','2756','2385','1468','4173','2640','6596','3685']
        listed={'1464','6908','2385','1468'}
        universe=[{'code':c,'market':'TWSE' if c in listed else 'TPEX'} for c in codes]
        count,calls=self.replay(universe,codes)
        self.assertEqual(count,12)
        self.assertEqual({c for c,m in calls},listed)

    def test_unknown_missing_or_conflicting_market_is_not_guessed(self):
        cases=[[],[{'code':'2330','market':'unknown'}],
               [{'code':'2330','market':'TWSE'},{'code':'2330','market':'TPEX'}]]
        for universe in cases:
            with self.subTest(universe=universe):
                self.assertEqual(self.replay(universe,['2330']), (0,[]))

    def test_filter_before_limit_preserves_budget_for_listed_symbols(self):
        codes=['5457','2330']
        universe=[{'code':'5457','market':'TPEX'},{'code':'2330','market':'TWSE'}]
        count,calls=self.replay(universe,codes,max_codes=1)
        self.assertEqual(count,3)
        self.assertEqual({c for c,m in calls},{'2330'})

    def test_identical_listing_duplicates_are_harmless(self):
        rows=[{'code':'2330','market':'TWSE'}]*2
        count,calls=self.replay(rows,['2330','2330'])
        self.assertEqual(count,3)
        self.assertEqual(len(calls),3)

if __name__=='__main__':unittest.main()
