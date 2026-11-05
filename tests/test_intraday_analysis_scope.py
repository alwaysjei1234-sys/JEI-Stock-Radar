"""An intraday coverage threshold never makes unrefreshed closes current."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
from scripts import update_system as u

class IntradayAnalysisScopeTests(unittest.TestCase):
    def test_main_uses_only_live_stocks_for_breadth_sectors_and_candidates(self):
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return cls(2026,11,5,10,0,tzinfo=u.TZ)
        rows=[]
        for i in range(1000):
            pct=1 if i<300 else -1 if i<600 else 9
            rows.append({'code':str(1000+i),'name':'fixture','market':'TWSE','date':'1151104',
                         'close':100+pct,'change':pct,'pct':pct,'open':100,'high':100+pct if pct>0 else 100,
                         'low':99,'value':100000000,'volume':1000000})
        def live(actual,**kwargs):
            for r in actual[:600]:r.update(live=True,quote_time='2026-11-05 09:59:50')
            return actual,600,-1,[],{}
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'system.json';hist=Path(temp)/'history.json';daily=Path(temp)/'daily.json'
            out.write_text('{"holdings":{},"risk":{},"data_date":"2026-11-04"}');hist.write_text('[]');daily.write_text('{"schema":1,"days":{}}')
            with patch.object(u,'OUT',out),patch.object(u,'HISTORY',hist),patch.object(u,'DAILY_PRICES',daily),patch.object(u,'datetime',Clock),patch.object(u,'fetch_initial_market_sources',return_value=(rows,[],[])),patch.object(u,'norm_twse',side_effect=lambda x:x),patch.object(u,'fetch_latest_offhours_close',side_effect=lambda rows,*args:(rows,None)),patch.object(u,'fetch_json',side_effect=RuntimeError('no current official data')),patch.object(u,'fetch_twse_daily',side_effect=RuntimeError('no current close')),patch.object(u,'fetch_institutional',return_value=({},['no current institutions'],{})),patch.object(u,'enrich_live',side_effect=live),patch.object(u,'backfill_twse_history',side_effect=lambda history,*args:(history,[])),patch.object(u,'build_sector_stats',wraps=u.build_sector_stats) as sectors,contextlib.redirect_stdout(io.StringIO()):
                u.main()
                snap=json.loads(out.read_text())
            self.assertEqual(len(sectors.call_args.args[0]),600)
            self.assertEqual(snap['risk']['breadth'],50)
            self.assertEqual(snap['market']['live_coverage_pct'],60)
            self.assertEqual(snap['market']['close_count'],1000)
            for group in ['attack','next','monster','tomorrow_monster','future_monster']:
                self.assertTrue(all(int(r['code'])<1600 for r in snap[group]))
            self.assertIn('已驗證盤中樣本',snap['market']['brief'])

if __name__=='__main__':unittest.main()
