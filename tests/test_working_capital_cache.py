import copy
import unittest
from datetime import date,datetime,timedelta,timezone
from urllib.error import URLError,HTTPError
from scripts import update_working_capital as w
import test_working_capital as fixture


class WorkingCapitalCacheTests(unittest.TestCase):
    now=datetime(2026,11,4,7,tzinfo=timezone.utc)

    def previous(self):
        r=w.parse_filing(fixture.WorkingCapitalTests().filing(),'6150',2026,2,date(2026,11,4))
        r.update(observed_at='2026-11-04T06:00:00+00:00',
            source_url=w.BASE+'?functionName=t164sb01&step=9&co_id=6150&year=2026&season=2&report_id=C')
        return {'schema':1,'rule_version':w.VERSION,'records':{'6150':r}}

    def build(self,previous,error=None,now=None,period='2026-Q2'):
        def fetch(*args):raise error or URLError('PRIVATE network detail')
        return w.build({'holdings':{'6150':{'qty':999}}},
            {'markets':{'otc':{'6150':{'financials':{'period':period}}}}},
            now or self.now,fetch,previous)['records']['6150']

    def test_transient_failure_preserves_original_observation_as_readonly(self):
        before=self.previous();r=self.build(before)
        self.assertEqual(r['status'],'cached')
        self.assertEqual(r['observed_at'],before['records']['6150']['observed_at'])
        self.assertEqual(r['current'],before['records']['6150']['current'])
        self.assertEqual(r['source_sha256'],before['records']['6150']['source_sha256'])
        self.assertEqual(r['last_checked_at'],self.now.isoformat(timespec='seconds'))
        self.assertEqual(r['alerts'],[])
        self.assertFalse(r['source_revalidated'])
        self.assertNotIn('PRIVATE',str(r))

    def test_cached_observation_never_renews_its_expiration(self):
        prior=self.previous();r=self.build(prior)
        again=self.build({'schema':1,'rule_version':w.VERSION,'records':{'6150':r}},now=self.now+timedelta(days=1))
        self.assertEqual(again['observed_at'],r['observed_at'])
        expired=self.build({'schema':1,'rule_version':w.VERSION,'records':{'6150':again}},now=self.now+timedelta(days=7))
        self.assertEqual(expired['status'],'unavailable')

    def test_unknown_private_fields_are_not_copied_at_any_level(self):
        prior=self.previous();prior['secret']='PRIVATE';r=prior['records']['6150']
        r.update(cost=123,qty=999,token='PRIVATE');r['current']['private_cost']=123
        kept=self.build(prior)
        self.assertEqual(kept['status'],'cached')
        for word in ('PRIVATE','private_cost',"'qty'","'cost'","'token'"):
            self.assertNotIn(word,str(kept))

    def test_future_naive_old_and_wrong_quarter_snapshots_are_refused(self):
        for stamp in ['2026-11-04T08:00:00+00:00','2026-11-04T06:00:00','2026-10-01T06:00:00+00:00','bad']:
            prior=self.previous();prior['records']['6150']['observed_at']=stamp
            self.assertEqual(self.build(prior)['status'],'unavailable')
        self.assertEqual(self.build(self.previous(),period='2026-Q3')['status'],'unavailable')

    def test_errors_indicating_parse_or_withdrawal_never_use_cache(self):
        for error in [ValueError('PRIVATE'),HTTPError('PRIVATE',404,'missing',{},None),HTTPError('PRIVATE',401,'denied',{},None),HTTPError('PRIVATE',403,'denied',{},None)]:
            self.assertEqual(self.build(self.previous(),error)['status'],'unavailable')
        for error in [HTTPError('PRIVATE',503,'down',{},None),HTTPError('PRIVATE',429,'limit',{},None),TimeoutError('PRIVATE')]:
            self.assertEqual(self.build(self.previous(),error)['status'],'cached')

    def test_company_unit_source_period_and_bad_values_are_refused(self):
        mutations=[('code','2330'),('unit','USD'),('source_url','https://example.com'),
            ('source_sha256','bad'),('period_end','2026-09-30'),('revenue_basis','quarter'),
            ('rule_version','other'),('not_for_historical_backtest',False),
            ('current',{'inventory':True}),('current',{'inventory':float('nan')}),
            ('current',{'inventory':-1}),('current',{'inventory':'100'})]
        for key,value in mutations:
            with self.subTest(key=key,value=value):
                prior=self.previous();prior['records']['6150'][key]=value
                self.assertEqual(self.build(prior)['status'],'unavailable')

    def test_invalid_prior_documents_and_no_cache_remain_explicit(self):
        for prior in [None,[],{}, {'schema':1,'rule_version':w.VERSION,'records':[]}, {'schema':1,'rule_version':w.VERSION,'records':{'6150':None}}]:
            self.assertEqual(self.build(prior)['status'],'unavailable')

    def test_success_replaces_cache_but_never_merges_old_missing_fields(self):
        prior=self.previous();fresh=copy.deepcopy(prior['records']['6150'])
        del fresh['current']['inventory'];fresh['status']='partial'
        result=w.build({'holdings':{'6150':{}}},{'markets':{'otc':{'6150':{'financials':{'period':'2026-Q2'}}}}},
            self.now,lambda *args:fresh,prior)['records']['6150']
        self.assertEqual(result['status'],'partial')
        self.assertNotIn('inventory',result['current'])
        self.assertEqual(result['observed_at'],self.now.isoformat(timespec='seconds'))


if __name__=='__main__':unittest.main()
