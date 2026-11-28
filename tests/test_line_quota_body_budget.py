"""Synthetic quota responses only: never contact LINE or send a message."""
import io
import json
import unittest
from unittest.mock import patch
from scripts import send_line_brief as line


class Clock:
    value = 0
    def now(self):
        return self.value
    def sleep(self, seconds):
        self.value += seconds


class Response(io.BytesIO):
    status = 200
    headers = {}
    def __init__(self, body, clock=None, declared=None):
        super().__init__(body)
        self.clock, self.declared = clock, declared
    def read(self, size=-1):
        if self.clock:
            self.clock.value += 100
        return super().read(size)
    def read1(self, size=-1):
        if self.clock:
            self.clock.value += 5
            return io.BytesIO.read(self, 1)
        return io.BytesIO.read(self, size)
    def getheader(self, name):
        return self.declared if name == 'Content-Length' else None


class LineQuotaBodyBudgetTests(unittest.TestCase):
    body = b'{"type":"limited","value":200}'

    def test_slow_quota_exhausts_without_any_push_or_secret_text(self):
        clock = Clock()
        replies = [Response(self.body,clock) for _ in range(3)]
        receipt = {'delivery_confirmed':False}
        with patch('time.monotonic',side_effect=clock.now), \
             patch.object(line.time,'sleep',side_effect=clock.sleep), \
             patch.object(line.urllib.request,'urlopen',side_effect=replies) as network:
            with self.assertRaises(RuntimeError) as error:
                line.push({'date':'2026-11-27'},'close','SYNTHETIC_TOKEN','U'+'a'*32,receipt)
        self.assertEqual(network.call_count,3)
        self.assertTrue(all(c.args[0].get_method() == 'GET' for c in network.call_args_list))
        self.assertTrue(all(r.closed for r in replies))
        self.assertEqual(receipt['stage'],'quota')
        self.assertFalse(receipt['delivery_confirmed'])
        self.assertNotIn('SYNTHETIC_TOKEN',str(error.exception))

    def test_connection_elapsed_time_counts_before_read(self):
        clock = Clock(); replies = [Response(self.body) for _ in range(3)]
        def connect(*args, **kwargs):
            clock.value += 13
            return replies.pop(0)
        with patch('time.monotonic',side_effect=clock.now), \
             patch.object(line.time,'sleep',side_effect=clock.sleep), \
             patch.object(line.urllib.request,'urlopen',side_effect=connect):
            with self.assertRaises(RuntimeError):
                line.api_get('/v2/bot/message/quota','SYNTHETIC_TOKEN')

    def test_oversized_valid_json_fails_closed_without_retry(self):
        response = Response(json.dumps({'padding':'x'*70000}).encode())
        with patch.object(line.urllib.request,'urlopen',return_value=response) as network:
            with self.assertRaises(ValueError):
                line.api_get('/v2/bot/message/quota','SYNTHETIC_TOKEN')
        self.assertEqual(network.call_count,1)
        self.assertTrue(response.closed)

    def test_parseable_truncation_never_authorizes_quota(self):
        response = Response(self.body,declared=str(len(self.body)+10))
        with patch.object(line.time,'sleep'), \
             patch.object(line.urllib.request,'urlopen',return_value=response) as network:
            with self.assertRaises(ValueError):
                line.api_get('/v2/bot/message/quota','SYNTHETIC_TOKEN')
        self.assertEqual(network.call_count,1)
        self.assertTrue(response.closed)

    def test_fast_complete_quota_keeps_existing_policy(self):
        quota = Response(self.body,declared=str(len(self.body)))
        consumption = Response(b'{"totalUsage":10}')
        with patch.object(line.urllib.request,'urlopen',side_effect=[quota,consumption]):
            self.assertTrue(line.quota_ok('SYNTHETIC_TOKEN'))
        self.assertTrue(quota.closed and consumption.closed)
