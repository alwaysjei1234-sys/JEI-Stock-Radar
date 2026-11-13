"""Service outages must not cause hundreds of doomed full-market requests."""
import copy
import unittest
from datetime import datetime
from unittest.mock import patch, call
from urllib.error import HTTPError, URLError
from scripts import update_system as u


class MisOutageProbeTests(unittest.TestCase):
    def rows(self, count=1967):
        return [{'code':str(1000+i), 'market':'TWSE' if i%2==0 else 'TPEX',
                 'close':100.0, 'pct':0.0} for i in range(count)]

    def test_persistent_503_limits_all_market_requests_and_keeps_prices(self):
        rows=self.rows(); original=copy.deepcopy(rows)
        error=HTTPError(u.TWSE_MIS,503,'unavailable',{},None)
        with patch.object(u,'fetch_mis_channels',side_effect=error) as fetch, patch.object(u.time,'sleep') as pause:
            result,count,index,errors,stats=u.enrich_live(rows,datetime(2026,11,4,10,tzinfo=u.TZ))
        self.assertEqual(fetch.call_count,3)
        self.assertEqual(pause.call_args_list,[call(1),call(2)])
        self.assertEqual(result,original)
        self.assertEqual((count,index),(0,None))
        self.assertTrue(stats['bulk_scan_skipped'])
        self.assertEqual(stats['skipped_channels'],1967)
        self.assertEqual(stats['unavailable_http_status'],503)
        self.assertEqual(stats['returned_messages'],0)
        self.assertIn('503',errors[0])
        for args in fetch.call_args_list:
            self.assertEqual(args.args[0],['tse_1000.tw','otc_1001.tw'])

    def test_denial_or_rate_limit_stops_after_one_probe(self):
        for status in (403,429):
            with self.subTest(status=status), patch.object(u,'fetch_mis_channels',side_effect=HTTPError(u.TWSE_MIS,status,'blocked',{},None)) as fetch, patch.object(u.time,'sleep') as pause:
                result,count,index,errors,stats=u.enrich_live(self.rows(),datetime(2026,11,4,10,tzinfo=u.TZ))
                self.assertEqual(fetch.call_count,1)
                pause.assert_not_called()
                self.assertEqual(count,0)
                self.assertTrue(stats['bulk_scan_skipped'])

    def test_transient_503_recovers_and_quotes_still_need_normal_gates(self):
        valid={'c':'2330','ex':'tse','ch':'2330.tw','d':'20261104','t':'09:59:00','z':'105','y':'100'}
        count=0
        def fetch(channels):
            nonlocal count
            count+=1
            if count==1:raise HTTPError(u.TWSE_MIS,503,'transient',{},None)
            if channels==['tse_t00.tw']:return []
            return [valid]
        rows=[{'code':'2330','market':'TWSE','close':100}]
        with patch.object(u,'fetch_mis_channels',side_effect=fetch),patch.object(u.time,'sleep'):
            result,live,index,errors,stats=u.enrich_live(rows,datetime(2026,11,4,10,tzinfo=u.TZ))
        self.assertEqual(live,1)
        self.assertEqual(result[0]['close'],105)
        self.assertEqual(stats['service_probe_attempts'],2)
        self.assertFalse(stats['bulk_scan_skipped'])

    def test_next_invocation_reprobes_after_outage_and_probe_prices_are_not_used(self):
        quote={'c':'2330','ex':'tse','ch':'2330.tw','d':'20261104','t':'09:59:00','z':'105','y':'100'}
        moment=datetime(2026,11,4,10,tzinfo=u.TZ)
        with patch.object(u,'fetch_mis_channels',side_effect=HTTPError(u.TWSE_MIS,503,'outage',{},None)),patch.object(u.time,'sleep'):
            self.assertTrue(u.enrich_live([{'code':'2330','market':'TWSE','close':100}],moment)[4]['bulk_scan_skipped'])
        with patch.object(u,'fetch_mis_channels',side_effect=[[quote],[{**quote,'d':'20261103'}],[]]) as fetch:
            result,count,index,errors,stats=u.enrich_live([{'code':'2330','market':'TWSE','close':100}],moment)
        self.assertEqual(fetch.call_count,3)
        self.assertFalse(stats['bulk_scan_skipped'])
        self.assertEqual(count,0,'probe response cannot inflate verified live coverage')
        self.assertEqual(result[0]['close'],100)

    def test_empty_probe_and_unrecognized_http_preserve_batch_recovery(self):
        for result in ([],HTTPError(u.TWSE_MIS,404,'unknown',{},None)):
            with self.subTest(result=type(result).__name__),patch.object(u,'fetch_mis_channels',side_effect=[result] if isinstance(result,Exception) else None,return_value=result):
                self.assertTrue(u.mis_service_probe(['tse_2330.tw'])[0])

    def test_invalid_envelope_is_bounded_before_bulk_scan(self):
        with patch.object(u,'fetch_mis_channels',side_effect=ValueError('unparseable')) as fetch,patch.object(u.time,'sleep'):
            self.assertEqual(u.mis_service_probe(['tse_2330.tw']),(False,3,'invalid_response'))
        self.assertEqual(fetch.call_count,3)

    def test_mixed_server_and_transport_outage_stops_after_three_attempts(self):
        errors=[HTTPError(u.TWSE_MIS,503,'unavailable',{},None),
                URLError('unavailable'),TimeoutError('unavailable')]
        with patch.object(u,'fetch_mis_channels',side_effect=errors) as fetch,patch.object(u.time,'sleep'):
            self.assertEqual(u.mis_service_probe(['tse_2330.tw']),(False,3,'network'))
        self.assertEqual(fetch.call_count,3)

    def test_other_server_errors_are_bounded_but_success_recovers(self):
        for code in (500,502,504):
            error=HTTPError(u.TWSE_MIS,code,'unavailable',{},None)
            with self.subTest(code=code),patch.object(u,'fetch_mis_channels',side_effect=error) as fetch,patch.object(u.time,'sleep'):
                self.assertEqual(u.mis_service_probe(['tse_2330.tw']),(False,3,code))
                self.assertEqual(fetch.call_count,3)
        with patch.object(u,'fetch_mis_channels',side_effect=[URLError('transient'),[]]),patch.object(u.time,'sleep'):
            self.assertEqual(u.mis_service_probe(['tse_2330.tw']),(True,2,None))

    def test_empty_universe_does_not_probe_network(self):
        with patch.object(u,'fetch_mis_channels') as fetch:
            self.assertEqual(u.mis_service_probe([]),(True,0,None))
        fetch.assert_not_called()

    def test_full_updater_retains_readonly_close_during_real_probe_outage(self):
        import test_midnight_archive_recovery as fixture
        actual_enrich=u.enrich_live
        with patch.object(u,'fetch_mis_channels',side_effect=HTTPError(u.TWSE_MIS,503,'unavailable',{},None)) as fetch,patch.object(u.time,'sleep'):
            snapshots=fixture.MidnightArchiveRecoveryTests().exercise(
                [datetime(2026,11,4,9,5,tzinfo=u.TZ)],live_impl=actual_enrich)
        self.assertEqual(fetch.call_count,3)
        market=snapshots[0]['market']
        self.assertEqual(market['session_status'],'盤中資料不足')
        self.assertTrue(market['live_diagnostics']['mis_stats']['bulk_scan_skipped'])
        self.assertFalse(market['live_valid'])
