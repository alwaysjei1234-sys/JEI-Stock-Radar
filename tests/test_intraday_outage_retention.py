"""A failed refresh cannot manufacture a lower risk from an empty live sample."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from scripts import update_system as u

class IntradayOutageRetentionTests(unittest.TestCase):
    now = datetime(2026,11,6,10,2,tzinfo=u.TZ)
    def snapshot(self):
        return {'schema':4,'updated_at':'2026-11-06 09:03','data_date':'2026-11-06',
            'summary':'verified snapshot','risk':{'score':100,'level':'red','label':'高風險防守','actionable':True,'as_of':'2026-11-06','cash':'70%↑'},
            'market':{'mode':'盤中即時','stale':False,'live_valid':True,'live_count':600,'close_count':1000,'live_coverage_pct':60,
                'analysis_scope':{'mode':'verified_live_sample','count':600,'universe_count':1000}},
            'holdings':{},'priority':[],'attack':[],'next':[],'monster':[],'rotate':[],'flow':[],'sectors':[],'backtest':{}}
    def diagnostic(self):return {'valid_trades':0,'coverage_pct':0,'mis_stats':{'bulk_scan_skipped':True},'errors':['MIS HTTP 503']}
    def run_main(self,count=0):
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return cls(2026,11,6,10,2,tzinfo=u.TZ)
        rows=[{'code':str(1000+i),'name':'fixture','market':'TWSE' if i<500 else 'TPEX','date':'1151105',
               'close':99,'change':-1,'pct':-1,'open':100,'high':100,'low':99,'value':100000000,'volume':1000000}for i in range(1000)]
        def live(actual,**kwargs):
            for row in actual[:count]:row.update(live=True,quote_time='2026-11-06 10:01:50')
            return actual,count,-1 if count else None,[] if count else ['MIS HTTP 503'],{'bulk_scan_skipped':not bool(count)}
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'system.json';hist=Path(temp)/'history.json';daily=Path(temp)/'daily.json'
            out.write_text(json.dumps(self.snapshot()));hist.write_text('[]');daily.write_text('{"schema":1,"days":{}}')
            with patch.object(u,'OUT',out),patch.object(u,'HISTORY',hist),patch.object(u,'DAILY_PRICES',daily),patch.object(u,'datetime',Clock),patch.object(u,'fetch_initial_market_sources',return_value=(rows,[],[])),patch.object(u,'norm_twse',side_effect=lambda x:x),patch.object(u,'fetch_latest_offhours_close',side_effect=lambda rows,*args:(rows,None)),patch.object(u,'fetch_json',side_effect=RuntimeError('no current official data')),patch.object(u,'fetch_twse_daily',side_effect=RuntimeError('no current close')),patch.object(u,'fetch_institutional',return_value=({},['no current institutions'],{})),patch.object(u,'enrich_live',side_effect=live),patch.object(u,'backfill_twse_history',side_effect=lambda history,*args:(history,[])),contextlib.redirect_stdout(io.StringIO()):
                u.main();snap=json.loads(out.read_text())
            return snap,json.loads(hist.read_text())
    def test_main_preserves_verified_risk_and_time_after_live_outage(self):
        snap,history=self.run_main()
        self.assertEqual(snap['risk']['score'],100)
        self.assertEqual(snap['updated_at'],'2026-11-06 09:03')
        self.assertFalse(snap['risk']['actionable'])
        self.assertTrue(snap['market']['no_new_picks'])
        self.assertEqual(snap['market']['live_count'],0)
        self.assertEqual(snap['market']['status_updated_at'],'2026-11-06 10:02')
        self.assertEqual(history,[])
    def test_new_verified_sample_can_replace_the_old_warning(self):
        snap,_=self.run_main(600)
        self.assertTrue(snap['market']['live_valid'])
        self.assertTrue(snap['risk']['actionable'])
        self.assertNotIn('retained_intraday_snapshot',snap['market'])
        self.assertEqual(snap['updated_at'],'2026-11-06 10:02')
        self.assertLess(snap['risk']['score'],100)
    def test_repeated_outage_preserves_original_snapshot_and_does_not_mutate_input(self):
        old=self.snapshot();before=copy.deepcopy(old)
        first=u.retained_intraday_snapshot(old,self.now,self.diagnostic())
        later=self.now.replace(hour=11)
        again=u.retained_intraday_snapshot(first,later,self.diagnostic())
        self.assertEqual(old,before)
        self.assertEqual(again['updated_at'],old['updated_at'])
        self.assertEqual(again['risk']['score'],100)
        self.assertEqual(again['market']['retained_intraday_snapshot'],first['market']['retained_intraday_snapshot'])
        self.assertFalse(again['market']['live_valid'])
        self.assertTrue(again['market']['historical_readonly'])
    def test_invalid_previous_snapshot_is_not_promoted(self):
        for change in [{'schema':3},{'data_date':'2026-11-05'},{'updated_at':'2026-11-06 10:03'},
                       {'holdings':{'2330':{'cost':100}}},{'risk':{'score':True}},
                       {'risk':{'score':float('nan'),'as_of':'2026-11-06'}}]:
            with self.subTest(change=change):
                old=self.snapshot();old.update(change)
                self.assertIsNone(u.retained_intraday_snapshot(old,self.now,self.diagnostic()))
        for change in [{'mode':'今日收盤'},{'live_count':True},{'live_count':499},
                       {'live_coverage_pct':34.9},{'live_valid':False},{'stale':True}]:
            with self.subTest(market=change):
                old=self.snapshot();old['market'].update(change)
                self.assertIsNone(u.retained_intraday_snapshot(old,self.now,self.diagnostic()))
    def test_no_cross_day_or_future_reuse(self):
        for now in [self.now.replace(day=7),self.now.replace(hour=8),self.now.replace(tzinfo=None)]:
            with self.subTest(now=now):
                self.assertIsNone(u.retained_intraday_snapshot(self.snapshot(),now,self.diagnostic()))

if __name__=='__main__':unittest.main()
