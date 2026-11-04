import copy
import unittest
from datetime import date,datetime
from unittest.mock import patch
from scripts import update_system as u


class TpexDatedCloseTests(unittest.TestCase):
    day=date(2026,11,4)

    def payload(self,n=550):
        fields=['代號','名稱','收盤','漲跌','開盤','最高','最低','成交股數','成交金額(元)']
        rows=[[str(3000+i),'測試股','101.5','+1.5','100','102','99','1,000,000','101,500,000'] for i in range(n)]
        return {'stat':'ok','date':'20261104','tables':[{'date':'115/11/04','fields':fields,'data':rows}]}

    def test_full_normalization_preserves_ohlcv_names_and_signed_changes(self):
        p=self.payload();p['tables'][0]['data'][0][3]='-1.5 '
        r=u.parse_tpex_dated_quotes(p,self.day)[0]
        self.assertEqual(r['date'],'2026-11-04');self.assertEqual(r['market'],'TPEX')
        self.assertEqual(r['name'],'測試股');self.assertEqual(r['value'],101500000)
        self.assertEqual(r['volume'],1000000);self.assertEqual(r['open'],100)
        self.assertAlmostEqual(r['pct'],-1.5/103*100)
        self.assertTrue(u.stock_only(r))

    def test_reordered_columns_use_names_not_fixed_positions(self):
        p=self.payload();t=p['tables'][0]
        t['fields']=t['fields'][::-1];t['data']=[r[::-1] for r in t['data']]
        r=u.parse_tpex_dated_quotes(p,self.day)[0]
        self.assertEqual(r['code'],'3000');self.assertEqual(r['close'],101.5)

    def test_empty_undated_management_table_is_not_a_dated_observation(self):
        p=self.payload();empty=copy.deepcopy(p['tables'][0]);empty.update(date=None,data=[],title='管理股票')
        p['tables'].append(empty)
        self.assertEqual(len(u.parse_tpex_dated_quotes(p,self.day)),550)
        empty['data']=[p['tables'][0]['data'][0]]
        with self.assertRaisesRegex(RuntimeError,'date mismatch'):u.parse_tpex_dated_quotes(p,self.day)

    def test_root_and_table_dates_are_both_mandatory(self):
        for where,value in [('root','20261103'),('root',None),('table','115/11/03'),('table',None)]:
            p=self.payload()
            if where=='root':p['date']=value
            else:p['tables'][0]['date']=value
            with self.assertRaisesRegex(RuntimeError,'date mismatch'):u.parse_tpex_dated_quotes(p,self.day)

    def test_wrong_status_missing_columns_and_small_response_are_refused(self):
        p=self.payload();p['stat']='no data'
        with self.assertRaises(RuntimeError):u.parse_tpex_dated_quotes(p,self.day)
        p=self.payload();p['tables'][0]['fields'][3]='unknown'
        with self.assertRaisesRegex(RuntimeError,'columns'):u.parse_tpex_dated_quotes(p,self.day)
        with self.assertRaisesRegex(RuntimeError,'coverage'):u.parse_tpex_dated_quotes(self.payload(30),self.day)

    def test_finite_prices_and_ordinary_stock_coverage_cannot_be_faked_by_etfs(self):
        p=self.payload();p['tables'][0]['data']=[['00937B','ETF','14.2','0.01','14.1','14.3','14','100','1420']]*550
        with self.assertRaisesRegex(RuntimeError,'coverage'):u.parse_tpex_dated_quotes(p,self.day)
        p=self.payload();p['tables'][0]['data'][0][2]='NaN'
        self.assertEqual(len(u.parse_tpex_dated_quotes(p,self.day)),549)

    def test_conflicting_duplicate_codes_are_rejected(self):
        p=self.payload();other=p['tables'][0]['data'][0].copy();other[2]='102'
        p['tables'][0]['data'].append(other)
        with self.assertRaisesRegex(RuntimeError,'conflicting duplicate'):u.parse_tpex_dated_quotes(p,self.day)

    def test_etf_symbol_is_preserved_but_warrants_are_excluded(self):
        p=self.payload();t=p['tables'][0]
        for code in ['00937B','700001']:t['data'].append([code,'fixture','14.2','0.01','14','15','13','100','1420'])
        rows=u.parse_tpex_dated_quotes(p,self.day)
        self.assertIn('00937B',[r['code'] for r in rows]);self.assertNotIn('700001',[r['code'] for r in rows])

    def test_valid_primary_response_does_not_request_broken_legacy_sources(self):
        with patch.object(u,'fetch_json_fast',return_value=self.payload()) as fetch:
            rows=u.fetch_tpex_daily(self.day)
        self.assertEqual(fetch.call_count,1)
        self.assertIn('/www/zh-tw/afterTrading/dailyQuotes?',fetch.call_args.args[0])
        self.assertEqual(len(rows),550)

    def test_new_response_failure_keeps_existing_safe_fallback(self):
        latest=[{'Date':'1151104','SecuritiesCompanyCode':str(3000+i),'Close':'101.5'} for i in range(550)]
        with patch.object(u,'fetch_json_fast',side_effect=[self.payload(5),{'aaData':[]},latest]):
            self.assertEqual(len(u.fetch_tpex_daily(self.day)),550)

    def test_offhours_merges_both_markets_only_for_verified_shared_date(self):
        twse=[{'date':'20261104','code':str(1000+i),'name':'TWSE','market':'TWSE','close':100,'pct':1,'value':1e8} for i in range(550)]
        with patch.object(u,'fetch_twse_daily',return_value=twse),patch.object(u,'fetch_json_fast',return_value=self.payload()):
            rows,day=u.fetch_latest_offhours_close([],datetime(2026,11,4,15,tzinfo=u.TZ),'2026-11-03')
        self.assertEqual(day,'2026-11-04');self.assertEqual(len(rows),1100)
        self.assertEqual(sum(r['market']=='TPEX' and u.stock_only(r) for r in rows),550)

    def test_offhours_still_refuses_wrong_twse_day(self):
        twse=[{'date':'20261103','code':str(1000+i),'market':'TWSE','close':100} for i in range(550)]
        with patch.object(u,'fetch_twse_daily',return_value=twse),patch.object(u,'fetch_json_fast',return_value=self.payload()):
            rows,day=u.fetch_latest_offhours_close([],datetime(2026,11,4,15,tzinfo=u.TZ),'2026-11-03')
        self.assertIsNone(day);self.assertEqual(rows,[])


if __name__=='__main__':unittest.main()
