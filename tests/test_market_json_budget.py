"""Slow successful reads must not indefinitely delay official-source fallback."""
import io
import json
import unittest
from unittest.mock import patch
from scripts import update_system as u


class Clock:
    value = 0.0
    def now(self):
        return self.value


class Drip(io.BytesIO):
    def __init__(self, clock, step=0.04):
        super().__init__(b'{"data": [1, 2, 3]}')
        self.clock = clock
        self.step = step
        self.chunks = 0
    def read(self, size=-1):
        self.clock.value += 100
        return super().read(size)
    def read1(self, size=-1):
        self.clock.value += self.step
        self.chunks += 1
        return io.BytesIO.read(self, 1)


class MarketJsonBudgetTests(unittest.TestCase):
    def test_slow_response_cannot_succeed_after_attempt_budget(self):
        for fetch in (u.fetch_json_fast, u.fetch_json):
            with self.subTest(fetch=fetch.__name__):
                clock = Clock(); slow = Drip(clock, step=2)
                with patch.object(u.time, 'monotonic', side_effect=clock.now), \
                     patch.object(u.urllib.request, 'urlopen', return_value=slow):
                    with self.assertRaises(TimeoutError):
                        fetch('https://example.invalid/public', tries=1)
                self.assertTrue(slow.closed)

    def test_fast_complete_response_keeps_bom_json_compatibility(self):
        for fetch in (u.fetch_json_fast, u.fetch_json):
            response = io.BytesIO(b'\xef\xbb\xbf{"data":[1,2,3]}')
            with patch.object(u.urllib.request, 'urlopen', return_value=response):
                self.assertEqual(fetch('https://example.invalid/public', tries=1), {'data':[1,2,3]})
            self.assertTrue(response.closed)

    def test_connection_time_counts_and_partial_json_never_publishes(self):
        clock = Clock(); response = io.BytesIO(b'{"data":[]}')
        def connect(*args, **kwargs):
            clock.value += 20
            return response
        with patch.object(u.time, 'monotonic', side_effect=clock.now), \
             patch.object(u.urllib.request, 'urlopen', side_effect=connect):
            with self.assertRaises(TimeoutError):u.fetch_json_fast('https://example.invalid/public',timeout=8)
        self.assertTrue(response.closed)

    def test_failed_attempt_can_retry_with_independent_budget(self):
        clock = Clock(); slow = Drip(clock); good = io.BytesIO(b'{"data":[]}')
        with patch.object(u.time, 'monotonic', side_effect=clock.now), \
             patch.object(u.urllib.request, 'urlopen', side_effect=[slow,good]):
            self.assertEqual(u.fetch_json_fast('https://example.invalid/public',timeout=0.05,tries=2),{'data':[]})
        self.assertEqual(slow.chunks,2)
        self.assertTrue(slow.closed and good.closed)

    def test_truncated_content_length_rejected_even_if_json_parses(self):
        class Truncated(io.BytesIO):
            def getheader(self, name):return '100'
        with patch.object(u.urllib.request,'urlopen',return_value=Truncated(b'{"data":[]}')):
            with self.assertRaisesRegex(ValueError,'incomplete'):
                u.fetch_json_fast('https://example.invalid/public')

    def test_tpex_slow_dated_endpoint_reaches_date_checked_backup(self):
        from datetime import date
        clock=Clock();slow=Drip(clock,step=2)
        old=io.BytesIO(b'{"aaData":[]}')
        latest=io.BytesIO(json.dumps([{'Date':'1151120','SecuritiesCompanyCode':str(1000+i),
                                      'Close':'10'} for i in range(500)]).encode())
        with patch.object(u.time,'monotonic',side_effect=clock.now), \
             patch.object(u.urllib.request,'urlopen',side_effect=[slow,old,latest]) as network:
            rows=u.fetch_tpex_daily(date(2026,11,20))
        self.assertEqual(len(rows),500)
        self.assertTrue(all(row['close']==10 for row in rows))
        self.assertEqual(network.call_count,3)
        self.assertTrue(slow.closed and old.closed and latest.closed)


if __name__ == '__main__':unittest.main()
