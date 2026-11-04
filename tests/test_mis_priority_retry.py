"""Tracked symbols get bounded recovery without weakening executed-trade gates."""
import copy
import unittest
from datetime import datetime
from unittest.mock import patch
from scripts import update_system as u


class MisPriorityRetryTests(unittest.TestCase):
    now=datetime(2026,11,4,11,45,tzinfo=u.TZ)

    def quote(self,code,**changes):
        return dict({'c':code,'d':'20261104','t':'11:44:00','z':'-',
                     'y':'100','v':'200'},**changes)

    def rows(self):
        return [{'code':str(1000+i),'market':'TWSE','close':100.0} for i in range(120)]+[
            {'code':'6150','market':'TPEX','close':100.0}]

    def test_tracked_symbol_beyond_first_100_gets_slot_without_extra_budget(self):
        rows=self.rows(); by={r['code']:r for r in rows}
        quotes=[self.quote(r['code']) for r in rows]
        old,_=u.select_mis_retry_channels(quotes,by,self.now)
        new,priority=u.select_mis_retry_channels(quotes,by,self.now,['6150'])
        self.assertNotIn('otc_6150.tw',old)
        self.assertEqual(new[0],'otc_6150.tw')
        self.assertEqual(len(new),100)
        self.assertEqual(priority,{'6150'})

    def test_duplicates_stale_zero_volume_and_unknown_symbols_waste_no_slots(self):
        rows=self.rows();by={r['code']:r for r in rows}
        messages=[self.quote('1000')]*110+[
            self.quote('1001',d='20261103'),self.quote('1002',t='11:34:59'),
            self.quote('1003',v='0'),self.quote('9999'),self.quote('6150')]
        channels,priority=u.select_mis_retry_channels(messages,by,self.now,['6150'])
        self.assertEqual(channels,['otc_6150.tw','tse_1000.tw'])

    def test_valid_price_duplicate_needs_no_missing_price_retry(self):
        by={'6150':{'market':'TPEX'}}
        for quotes in ([self.quote('6150'),self.quote('6150',z='101')],
                       [self.quote('6150',z='101'),self.quote('6150')]):
            self.assertEqual(u.select_mis_retry_channels(quotes,by,self.now,['6150']),( [],set()))

    def test_untrusted_priority_values_never_create_channels(self):
        by={'6150':{'market':'TPEX'},'00937B':{'market':'TPEX'}}
        channels,priority=u.select_mis_retry_channels(
            [self.quote('6150'),self.quote('00937B')],by,self.now,
            [None,True,6150,'6150|tse_2330.tw','00937B','absent'])
        self.assertEqual(channels,['otc_6150.tw'])
        self.assertFalse(priority)

    def exercise(self,changed):
        rows=self.rows();original=copy.deepcopy(rows)
        def fetch(channels):
            if len(channels)==2 and channels[0]=='tse_1000.tw': return []  # probe
            if channels==['tse_t00.tw']:return []
            if len(channels)==20:
                return [self.quote('6150',**changed)] if 'otc_6150.tw' in channels else []
            return [self.quote(c.split('_')[1][:-3]) for c in channels]
        with patch.object(u,'fetch_mis_channels',side_effect=fetch):
            result,count,index,errors,stats=u.enrich_live(rows,self.now,priority_codes=['6150'])
        return result,count,stats,original

    def test_full_scan_recovers_tracked_trade_and_counts_only_verified_recovery(self):
        rows,count,stats,_=self.exercise({'z':'101.5'})
        self.assertEqual(count,1)
        self.assertEqual(rows[-1]['close'],101.5)
        self.assertEqual(stats['retry_requested'],100)
        self.assertEqual(stats['priority_retry_requested'],1)
        self.assertEqual(stats['priority_retry_recovered'],1)
        self.assertEqual(stats['retry_recovered'],1)

    def test_recovered_bad_date_time_price_and_previous_close_are_not_counted(self):
        for changes in ({'z':'101','d':'20261103'},{'z':'101','t':'11:34:59'},
                        {'z':'101','t':'11:46:01'},{'z':'NaN'},
                        {'z':'101','y':'-'},{'z':'101','y':True}):
            with self.subTest(changes=changes):
                rows,count,stats,original=self.exercise(changes)
                self.assertEqual(count,0)
                self.assertEqual(rows,original)
                self.assertEqual(stats['priority_retry_recovered'],0)
                self.assertEqual(stats['retry_recovered'],0)

    def test_retry_cannot_inject_an_unrequested_symbol(self):
        rows=[{'code':'6150','market':'TPEX','close':100},
              {'code':'2330','market':'TWSE','close':100}]
        calls=0
        def fetch(channels):
            nonlocal calls
            calls+=1
            if calls==1:return []
            if calls==2:return [self.quote('6150')]
            if calls==3:return [self.quote('2330',z='101')]
            return []
        with patch.object(u,'fetch_mis_channels',side_effect=fetch):
            _,count,_,_,stats=u.enrich_live(rows,self.now,['6150'])
        self.assertEqual(count,0)
        self.assertEqual(stats['retry_recovered'],0)

    def test_unavailable_service_still_stops_before_any_priority_retries(self):
        from urllib.error import HTTPError
        with patch.object(u,'fetch_mis_channels',side_effect=HTTPError(u.TWSE_MIS,503,'down',{},None)) as fetch,patch.object(u.time,'sleep'):
            _,count,_,_,stats=u.enrich_live(self.rows(),self.now,['6150'])
        self.assertEqual(fetch.call_count,3)
        self.assertEqual(count,0)
        self.assertTrue(stats['bulk_scan_skipped'])

    def test_main_uses_public_tickers_and_partial_recovery_stays_readonly(self):
        import test_midnight_archive_recovery as fixture
        original=fixture.MidnightArchiveRecoveryTests().prior()
        original['holdings']={'2330':{'score':42,'trend':'歷史觀察'}}
        actual=u.enrich_live
        received=[]
        calls=0
        def fetch(channels):
            nonlocal calls
            calls+=1
            if calls==1 or channels==['tse_t00.tw']:return []
            if calls==2:return [self.quote('2330'),self.quote('6488')]
            return [self.quote('2330',z='101')]
        def live(rows,priority_codes=()):
            received.extend(priority_codes)
            return actual(rows,self.now,priority_codes=priority_codes)
        with patch.object(fixture.MidnightArchiveRecoveryTests,'prior',return_value=original),patch.object(u,'fetch_mis_channels',side_effect=fetch):
            snap=fixture.MidnightArchiveRecoveryTests().exercise([self.now],live_impl=live)[0]
        self.assertEqual(received,['2330'])
        self.assertEqual(snap['market']['live_diagnostics']['mis_stats']['priority_retry_recovered'],1)
        self.assertEqual(snap['market']['partial_live']['quotes'][0]['code'],'2330')
        self.assertTrue(snap['market']['no_new_picks'])
        self.assertFalse(snap['market']['live_valid'])
        self.assertEqual(snap['data_date'],'2026-11-03')
        self.assertEqual(snap['holdings'],original['holdings'])


if __name__=='__main__':unittest.main()
