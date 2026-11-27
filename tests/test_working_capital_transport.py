"""Synthetic iXBRL HTTP faults; parsed values and fallback policy stay unchanged."""
import io
import unittest
from datetime import date
from unittest.mock import patch
from scripts import update_working_capital as w
from scripts import update_free_research as transport


class Clock:
    value=0
    def now(self):return self.value


class Response(io.BytesIO):
    def __init__(self,body=b'filing',clock=None,elapsed=0,length=None):
        super().__init__(body);self.clock=clock;self.elapsed=elapsed;self.length=length;self.read_sizes=[]
    def getheader(self,name):return self.length if name=='Content-Length' else None
    def read(self,size=-1):
        self.read_sizes.append(size)
        if self.clock:self.clock.value+=self.elapsed
        return super().read(size)
    read1=read


class FilingTransportTests(unittest.TestCase):
    def fetch(self,response,clock,connect_delay=0):
        def connect(*args,**kw):clock.value+=connect_delay;return response
        with patch.object(transport.time,'monotonic',clock.now),patch.object(w.urllib.request,'urlopen',side_effect=connect),patch.object(w,'parse_filing',return_value={'status':'comparable'}) as parser:
            value=w.fetch_record('2330','2026-Q3',date(2026,11,28))
            return value,parser.call_args

    def test_slow_body_never_reaches_filing_parser(self):
        clock=Clock();response=Response(clock=clock,elapsed=21)
        with self.assertRaises(TimeoutError):self.fetch(response,clock)
        self.assertTrue(response.closed)

    def test_connection_time_counts_before_reading_filing(self):
        clock=Clock();response=Response()
        with self.assertRaises(TimeoutError):self.fetch(response,clock,connect_delay=21)
        self.assertEqual(response.read_sizes,[])
        self.assertTrue(response.closed)

    def test_parseable_but_truncated_body_is_rejected_before_parser(self):
        clock=Clock();response=Response(length='1000')
        with self.assertRaises(ValueError):self.fetch(response,clock)
        self.assertTrue(response.closed)

    def test_valid_body_keeps_source_parameters_and_small_reads(self):
        response=Response(b'official filing',length='15');value,args=self.fetch(response,Clock())
        self.assertEqual(args.args,(b'official filing','2330',2026,3,date(2026,11,28)))
        self.assertIn('co_id=2330&year=2026&season=3',value['source_url'])
        self.assertTrue(response.read_sizes)
        self.assertTrue(all(n<=65536 for n in response.read_sizes))
        self.assertTrue(response.closed)

    def test_real_timeout_path_keeps_prior_observation_without_new_alert(self):
        import test_working_capital_cache as fixture
        prior=fixture.WorkingCapitalCacheTests().previous()
        now=fixture.WorkingCapitalCacheTests.now
        clock=Clock();response=Response(clock=clock,elapsed=21)
        with patch.object(transport.time,'monotonic',clock.now),patch.object(w.urllib.request,'urlopen',return_value=response):
            result=w.build({'holdings':{'6150':{}}},
                {'markets':{'otc':{'6150':{'financials':{'period':'2026-Q2'}}}}},
                now,previous=prior)['records']['6150']
        self.assertEqual(result['status'],'cached')
        self.assertEqual(result['observed_at'],prior['records']['6150']['observed_at'])
        self.assertEqual(result['source_sha256'],prior['records']['6150']['source_sha256'])
        self.assertEqual(result['alerts'],[])
        self.assertFalse(result['source_revalidated'])
        self.assertEqual(result['error_type'],'TimeoutError')
        self.assertTrue(response.closed)

    def test_oversized_filing_header_is_rejected_without_read(self):
        response=Response(length=str(w.LIMIT+1))
        with self.assertRaises(ValueError):self.fetch(response,Clock())
        self.assertEqual(response.read_sizes,[])
        self.assertTrue(response.closed)

if __name__=='__main__':unittest.main()
