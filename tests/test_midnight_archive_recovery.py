"""Exercise the actual updater twice across midnight without network or new trades."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from scripts import update_system as u
from scripts.validate_market_session import validate_session

TZ=ZoneInfo('Asia/Taipei')
class Clock(datetime):
    current=datetime(2026,11,4,0,44,tzinfo=TZ)
    @classmethod
    def now(cls,tz=None):return cls.current

class MidnightArchiveRecoveryTests(unittest.TestCase):
    def prior(self):
        return {'schema':4,'data_date':'2026-11-03','updated_at':'2026-11-03 23:55',
                'summary':'verified prior close','market':{'mode':'今日收盤','stale':False,'historical_readonly':False,'close_count':1967,'live_valid':False},
                'holdings':{},'attack':[{'code':'2330','score':88}],'sectors':[{'name':'fixture'}],
                'risk':{'score':26,'level':'green','label':'fixture','actionable':True,'as_of':'2026-11-03'}}

    def exercise(self,moments):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'system.json';history=Path(temp)/'history.json';daily=Path(temp)/'daily.json'
            original=self.prior();out.write_text(json.dumps(original));history.write_text('[]');daily.write_text('{"schema":1,"days":{}}')
            before=(history.read_bytes(),daily.read_bytes());snapshots=[]
            def get(url,*args,**kwargs):
                if url==u.TWSE_STOCK:return [{'Code':'2330','Name':'fixture','ClosingPrice':'100','Change':'1','Date':'1151103','TradeVolume':'1000000'}]
                if url.startswith(u.TPEX_STOCK):return [{'SecuritiesCompanyCode':'6488','CompanyName':'fixture','Close':'100','Change':'1','Date':'1151103','TradingShares':'1000000'}]
                if url==u.TWSE_INDEX:return []
                raise RuntimeError('No new official session in fixture')
            def offhours(rows,*args):return rows,None
            def live(rows):return rows,0,None,[],{}
            with patch.object(u,'OUT',out),patch.object(u,'HISTORY',history),patch.object(u,'DAILY_PRICES',daily),patch.object(u,'datetime',Clock),patch.object(u,'fetch_json',side_effect=get),patch.object(u,'fetch_latest_offhours_close',side_effect=offhours),patch.object(u,'fetch_institutional',return_value=({},['no new institutional session'],{})),patch.object(u,'enrich_live',side_effect=live),contextlib.redirect_stdout(io.StringIO()):
                for moment in moments:
                    Clock.current=moment
                    u.main()
                    current=json.loads(out.read_text());snapshots.append(current)
                    self.assertEqual(current['updated_at'],original['updated_at'],'status refresh must preserve original close verification time')
                    self.assertEqual(current['data_date'],original['data_date'])
                    self.assertEqual(current['attack'],original['attack'])
                    self.assertEqual(current['holdings'],original['holdings'])
                    self.assertEqual(current['market']['last_checked_at'],moment.strftime('%Y-%m-%d %H:%M'))
                    self.assertEqual(current['market']['status_updated_at'],moment.strftime('%Y-%m-%d %H:%M'))
                    self.assertTrue(current['market']['historical_readonly'])
                    self.assertTrue(current['market']['no_new_picks'])
                    self.assertFalse(current['risk']['actionable'])
                    self.assertEqual(current['market']['mode'],'最近收盤')
                    self.assertTrue(validate_session(current,moment.date()))
                    self.assertIsNotNone(u.validated_previous_close(current,moment))
                    self.assertEqual((history.read_bytes(),daily.read_bytes()),before,'no midnight candles or paper prices may be created')
            return snapshots

    def test_repeated_midnight_refresh_keeps_verified_close_readable(self):
        self.exercise([datetime(2026,11,4,0,44,tzinfo=TZ),datetime(2026,11,4,1,44,tzinfo=TZ)])

    def test_preopen_and_market_open_without_new_verified_trades_remain_readonly(self):
        self.exercise([datetime(2026,11,4,0,44,tzinfo=TZ),datetime(2026,11,4,8,45,tzinfo=TZ),datetime(2026,11,4,9,5,tzinfo=TZ)])

    def test_status_tracks_open_and_close_boundaries_without_changing_prices(self):
        moments=[datetime(2026,11,4,h,m,tzinfo=TZ)
                 for h,m in [(8,59),(9,0),(13,29),(13,30),(18,0)]]
        snapshots=self.exercise(moments)
        expected=['盤前準備','盤中資料不足','盤中資料不足',
                  '交易日資料待驗證','交易日資料待驗證']
        self.assertEqual([s['market']['session_status'] for s in snapshots],expected)
        for snapshot in snapshots:
            market=snapshot['market']
            self.assertIn(market['session_status'],market['brief'])
            self.assertIn(market['session_reason'],snapshot['summary'])
            self.assertEqual(market['live_diagnostics']['reason'],market['session_reason'])
        for snapshot in snapshots[:3]:
            self.assertNotIn('當日官方收盤尚未',snapshot['summary'])

    def test_weekend_still_overrides_preopen_and_live_hours(self):
        snapshots=self.exercise([datetime(2026,11,7,8,59,tzinfo=TZ),
                                 datetime(2026,11,7,9,5,tzinfo=TZ)])
        for snapshot in snapshots:
            self.assertEqual(snapshot['market']['session_status'],'休市')
            self.assertIn('週末',snapshot['market']['session_reason'])
            self.assertFalse(snapshot['market']['live_diagnostics']['attempted'])

if __name__=='__main__':unittest.main()
