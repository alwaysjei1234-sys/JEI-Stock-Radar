"""Synthetic MIS transport checks; no real alert or external request is sent."""
import io
import json
import unittest
from unittest.mock import patch
from scripts import update_system as u


class Clock:
    value = 0
    def now(self):
        return self.value


class Drip(io.BytesIO):
    def __init__(self, body, clock):
        super().__init__(body)
        self.clock = clock
    def read(self, size=-1):
        self.clock.value += 100
        return super().read(size)
    def read1(self, size=-1):
        self.clock.value += 1
        return io.BytesIO.read(self, min(size, 1))


class MisTransportBudgetTests(unittest.TestCase):
    def test_continuously_arriving_body_cannot_hold_mis_request(self):
        clock = Clock()
        response = Drip(b'{"rtcode":"0000","msgArray":[]}', clock)
        with patch.object(u.time, 'monotonic', clock.now), patch.object(
                u.urllib.request, 'urlopen', return_value=response):
            with self.assertRaises(TimeoutError):
                u.fetch_mis_channels(['tse_t00.tw'])
        self.assertTrue(response.closed)

    def test_connection_time_is_included_in_mis_budget(self):
        clock = Clock()
        response = io.BytesIO(b'{"rtcode":"0000","msgArray":[]}')
        def connect(*args, **kwargs):
            clock.value = 10
            return response
        with patch.object(u.time, 'monotonic', clock.now), patch.object(
                u.urllib.request, 'urlopen', side_effect=connect):
            with self.assertRaises(TimeoutError):
                u.fetch_mis_channels(['tse_t00.tw'])
        self.assertTrue(response.closed)

    def test_truncated_complete_json_is_not_a_successful_mis_response(self):
        class Truncated(io.BytesIO):
            def getheader(self, name):
                return '1000' if name == 'Content-Length' else None
        response = Truncated(b'{"rtcode":"0000","msgArray":[]}')
        with patch.object(u.urllib.request, 'urlopen', return_value=response):
            with self.assertRaises(ValueError):
                u.fetch_mis_channels(['tse_t00.tw'])
        self.assertTrue(response.closed)

    def test_failure_does_not_prevent_next_valid_utf8_response(self):
        clock = Clock()
        slow = Drip(b'{"rtcode":"0000","msgArray":[]}', clock)
        quotes = [{'c': '2330', 'n': '台積電'}]
        good = io.BytesIO(json.dumps({'rtcode':'0000','msgArray':quotes}, ensure_ascii=False).encode('utf-8-sig'))
        with patch.object(u.time, 'monotonic', clock.now), patch.object(
                u.urllib.request, 'urlopen', side_effect=[slow, good]):
            with self.assertRaises(TimeoutError):
                u.fetch_mis_channels(['tse_2330.tw'])
            self.assertEqual(u.fetch_mis_channels(['tse_2330.tw']), quotes)
        self.assertTrue(good.closed)
