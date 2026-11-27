"""Synthetic free-public API transport faults; no external API or secret."""
import io
import json
import unittest
from unittest.mock import patch
from scripts import update_free_research as u


class Clock:
    value=0
    def now(self):return self.value


class Response(io.BytesIO):
    def __init__(self, body, clock=None, seconds=0, length=None):
        super().__init__(body);self.clock=clock;self.seconds=seconds;self.length=length
    def getheader(self,name):return self.length if name=='Content-Length' else None
    def read(self,size=-1):
        if self.clock:self.clock.value+=self.seconds
        return super().read(size)
    def read1(self,size=-1):return self.read(size)


class ResearchTransportTests(unittest.TestCase):
    def test_slow_successful_body_is_not_accepted_after_attempt_budget(self):
        clock=Clock();responses=[Response(b'[]',clock,46) for _ in range(3)]
        with patch.object(u.time,'monotonic',clock.now),patch.object(u.time,'sleep'),patch.object(u.urllib.request,'urlopen',side_effect=responses):
            with self.assertRaises(RuntimeError):u.fetch_json(u.SOURCES['twseRevenue'])
        self.assertTrue(all(r.closed for r in responses))

    def test_connection_time_counts_before_body(self):
        clock=Clock();responses=[Response(b'[]') for _ in range(3)]
        def connect(*a,**kw):clock.value+=46;return responses.pop(0)
        with patch.object(u.time,'monotonic',clock.now),patch.object(u.time,'sleep'),patch.object(u.urllib.request,'urlopen',side_effect=connect):
            with self.assertRaises(RuntimeError):u.fetch_json(u.SOURCES['twseRevenue'])

    def test_complete_json_with_truncated_content_length_is_rejected(self):
        responses=[Response(b'[]',length='1000') for _ in range(3)]
        with patch.object(u.time,'sleep'),patch.object(u.urllib.request,'urlopen',side_effect=responses):
            with self.assertRaises(RuntimeError):u.fetch_json(u.SOURCES['twseRevenue'])
        self.assertTrue(all(r.closed for r in responses))

    def test_retry_recovers_with_valid_utf8_public_rows(self):
        clock=Clock();bad=Response(b'[]',clock,46)
        rows=[{'code':'2330','name':'台積電'}];good=Response(json.dumps(rows,ensure_ascii=False).encode('utf-8-sig'))
        with patch.object(u.time,'monotonic',clock.now),patch.object(u.time,'sleep'),patch.object(u.urllib.request,'urlopen',side_effect=[bad,good]) as request:
            self.assertEqual(u.fetch_json(u.SOURCES['twseRevenue']),rows)
        self.assertEqual(request.call_count,2)
        self.assertTrue(bad.closed and good.closed)

    def test_oversized_payload_is_rejected_with_bounded_reads(self):
        limit=16*1024*1024
        class Oversized(Response):
            def __init__(self):super().__init__(b'');self.sizes=[];self.remaining=limit+1
            def read(self,size=-1):
                self.sizes.append(size)
                if size<0:return b'['+b' '*(limit-1)+b']'
                n=min(size,self.remaining);self.remaining-=n
                return b' '*n
            read1=read
        responses=[Oversized() for _ in range(3)]
        with patch.object(u.time,'sleep'),patch.object(u.urllib.request,'urlopen',side_effect=responses):
            with self.assertRaises(RuntimeError):u.fetch_json(u.SOURCES['twseRevenue'])
        self.assertTrue(all(all(0<n<=65536 for n in r.sizes) for r in responses))

if __name__=='__main__':unittest.main()
