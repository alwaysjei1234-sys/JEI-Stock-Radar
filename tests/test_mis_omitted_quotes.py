"""A nonempty partial batch must not silently drop requested symbols."""
import unittest
from datetime import datetime
from unittest.mock import patch
from scripts import update_system as u

class MisOmittedQuotesTests(unittest.TestCase):
    now=datetime(2026,11,5,12,0,tzinfo=u.TZ)
    def quote(self,code,**changes):
        return dict(dict(c=code,ex='tse',ch=code+'.tw',d='20261105',t='11:59:00',z='101',y='100',v='20'),**changes)
    def scan(self, retry):
        calls=[]
        def fetch(channels):
            calls.append(channels)
            if channels==['tse_t00.tw']:return []
            if len(calls)==1:return [self.quote('2330')]
            return retry
        rows=[dict(code=c,market='TWSE',close=100) for c in ('2330','2317')]
        with patch.object(u,'mis_service_probe',return_value=(True,1,None)),patch.object(u,'fetch_mis_channels',side_effect=fetch):
            result=u.enrich_live(rows,self.now,priority_codes=['2317'])
        return result,calls
    def test_partial_batch_recovers_omitted_tracked_symbol(self):
        result,calls=self.scan([self.quote('2317')])
        self.assertEqual(result[1],2)
        self.assertIn(['tse_2317.tw'],calls)
        self.assertEqual(result[4]['priority_retry_recovered'],1)
        self.assertEqual(result[4]['omitted_symbols'],1)
    def test_bad_recovery_cannot_bypass_existing_gates(self):
        for changes in ({'d':'20261104'},{'t':'11:49:59'},{'ex':'otc'}, {'y':'-'},{'z':'-'},{'c':'9999','ch':'9999.tw'}):
            with self.subTest(changes=changes):
                result,_=self.scan([self.quote('2317',**changes)])
                self.assertEqual(result[1],1)
                self.assertEqual(result[0][1]['close'],100)
                self.assertEqual(result[4]['retry_recovered'],0)
    def test_shared_budget_prioritizes_omitted_tracked_symbol(self):
        rows={str(1000+i):{'market':'TWSE'} for i in range(120)}
        rows['2330']={'market':'TWSE'}
        quotes=[self.quote(c,z='-') for c in rows if c!='2330']
        channels,priority=u.select_mis_retry_channels(quotes,rows,self.now,['2330'],omitted_codes=['2330'])
        self.assertEqual(len(channels),100)
        self.assertEqual(channels[0],'tse_2330.tw')
        self.assertEqual(priority,{'2330'})
    def test_unrequested_and_invalid_omitted_codes_are_ignored(self):
        by={'2330':{'market':'TWSE'},'00937B':{'market':'TPEX'},'2317':{'market':'bad'}}
        channels,_=u.select_mis_retry_channels([],by,self.now,omitted_codes=['2330','2330',None,'9999','00937B','2317'])
        self.assertEqual(channels,['tse_2330.tw'])

if __name__=='__main__':unittest.main()
