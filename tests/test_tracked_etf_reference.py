import copy
import unittest
from scripts import update_system as u

DAY='2026-11-03'
class TrackedETFReferenceTests(unittest.TestCase):
    def setUp(self):
        self.prior={'2330':{'score':60,'as_of':DAY},'00937B':{'score':None,'as_of':'2026-10-27','reason':'old unverified levels','defense':14.11,'target':14.22}}
        self.row={'code':'00937B','date':'1151103','market':'TPEX','close':14.19}

    def test_same_day_official_bond_reference_clears_unverified_levels_and_keeps_stock(self):
        original=copy.deepcopy(self.prior)
        out=u.refresh_public_etf_references(self.prior,{'00937B':self.row},DAY)
        self.assertEqual(out['2330'],self.prior['2330'])
        self.assertEqual(out['00937B']['as_of'],DAY)
        self.assertIn('TPEx官方收盤14.19元',out['00937B']['reason'])
        for key in ['score','defense','target']:self.assertIsNone(out['00937B'][key])
        self.assertTrue(u.is_safe_public_holdings(out))
        self.assertEqual(self.prior,original)
        self.assertEqual(u.refresh_public_etf_references(out,{'00937B':self.row},DAY),out)

    def test_daily_refresh_advances_only_matching_new_official_date(self):
        first=u.refresh_public_etf_references(self.prior,{'00937B':self.row},DAY)
        row={**self.row,'date':'1151104','close':14.25}
        self.assertEqual(u.refresh_public_etf_references(first,{'00937B':row},DAY),first)
        second=u.refresh_public_etf_references(first,{'00937B':row},'2026-11-04')
        self.assertIn('14.25元',second['00937B']['reason'])
        self.assertEqual(second['00937B']['as_of'],'2026-11-04')
        self.assertEqual(u.refresh_public_etf_references(second,{'00937B':self.row},DAY),second)

    def test_wrong_or_missing_dates_live_quotes_and_unknown_sources_preserve_reference(self):
        for change in [{'date':'1151102'},{'date':'1151104'},{'date':None},{'date':'1151332'},{'live':True},{'market':'unverified'},{'code':'00679B'}]:
            with self.subTest(change=change):
                self.assertEqual(u.refresh_public_etf_references(self.prior,{'00937B':{**self.row,**change}},DAY),self.prior)

    def test_nonfinite_zero_negative_boolean_or_missing_price_is_not_a_close(self):
        for price in [None,0,-1,True,'NaN','Infinity',float('nan'),float('inf')]:
            with self.subTest(price=price):
                self.assertEqual(u.refresh_public_etf_references(self.prior,{'00937B':{**self.row,'close':price}},DAY),self.prior)

    def test_listed_etf_is_supported_but_untracked_etf_is_never_added(self):
        prior={'0050':{}}
        rows={'0050':{'code':'0050','date':'20261103','market':'TWSE','close':65.2},'00679B':{**self.row,'code':'00679B'}}
        result=u.refresh_public_etf_references(prior,rows,DAY)
        self.assertEqual(set(result),{'0050'})
        self.assertIn('TWSE官方收盤65.2元',result['0050']['reason'])
        self.assertIsNone(result['0050']['score'])

    def test_private_holdings_are_rejected(self):
        with self.assertRaises(ValueError):
            u.refresh_public_etf_references({'00937B':{'shares':1000}}, {'00937B':self.row},DAY)

    def test_invalid_asof_or_nonmap_rows_cannot_refresh(self):
        for asof,rows in [('2026-02-30',{'00937B':self.row}),(None,{}),(DAY,[])]:
            self.assertEqual(u.refresh_public_etf_references(self.prior,rows,asof),self.prior)


class UpdaterETFIntegrationTests(unittest.TestCase):
    def run_mode(self,when):
        import contextlib,io,json,tempfile
        from pathlib import Path
        from datetime import datetime
        from unittest.mock import patch
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return when
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'system.json';history=Path(temp)/'history.json';daily=Path(temp)/'daily.json'
            prior={'updated_at':'2026-11-03 14:30','data_date':DAY,'market':{'mode':'今日收盤','stale':False,'close_count':1967},'risk':{'score':70,'level':'yellow'},'holdings':{'2330':{'score':60,'as_of':DAY},'00937B':{'as_of':'2026-10-27','reason':'old'}},'attack':[],'sectors':[]}
            out.write_text(json.dumps(prior));history.write_text('[]');daily.write_text('{"schema":1,"kind":"official_daily_close","days":{}}')
            def get(url,*args,**kwargs):
                if url==u.TWSE_STOCK:return [{'Code':'2330','Name':'fixture','ClosingPrice':'100','Change':'1','Date':'1151103','TradeVolume':'1000000'}]
                if url.startswith(u.TPEX_STOCK):return [{'SecuritiesCompanyCode':'6488','CompanyName':'fixture','Close':'100','Change':'1','Date':'1151103','TradingShares':'1000000'},{'SecuritiesCompanyCode':'00937B','CompanyName':'fixture ETF','Close':'14.19','Change':'0.01','Date':'1151103','TradingShares':'1000000'}]
                if url==u.TWSE_INDEX:return []
                raise RuntimeError('no other official report in fixture')
            with patch.object(u,'OUT',out),patch.object(u,'HISTORY',history),patch.object(u,'DAILY_PRICES',daily),patch.object(u,'datetime',Clock),patch.object(u,'fetch_json',side_effect=get),patch.object(u,'fetch_latest_offhours_close',side_effect=lambda rows,*args:(rows,None)),patch.object(u,'fetch_institutional',return_value=({},['fixture unavailable'],{})),contextlib.redirect_stdout(io.StringIO()):
                u.main()
            result=json.loads(out.read_text())
            self.assertIn('TPEx官方收盤14.19元',result['holdings']['00937B']['reason'])
            self.assertEqual(result['holdings']['00937B']['as_of'],DAY)
            self.assertIsNone(result['holdings']['00937B']['score'])
            self.assertEqual(result['holdings']['2330'],prior['holdings']['2330'])
            self.assertTrue(u.is_safe_public_holdings(result['holdings']))
            self.assertFalse(any(row.get('code')=='00937B' for row in result.get('universe',[])))
            self.assertNotIn('00937B',daily.read_text())
            return result

    def test_main_refreshes_tracked_etf_after_verified_close(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        result=self.run_mode(datetime(2026,11,3,16,30,tzinfo=ZoneInfo('Asia/Taipei')))
        self.assertEqual(result['market']['mode'],'今日收盤')

    def test_main_refreshes_tracked_etf_in_overnight_readonly_snapshot(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        result=self.run_mode(datetime(2026,11,4,2,50,tzinfo=ZoneInfo('Asia/Taipei')))
        self.assertEqual(result['market']['mode'],'最近收盤')
        self.assertFalse(result['risk']['actionable'])
        self.assertEqual(result['updated_at'],'2026-11-03 14:30')

if __name__=='__main__':unittest.main()
