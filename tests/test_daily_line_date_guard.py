"""Exercise the real daily sender with synthetic time; never contact LINE."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts import send_line_brief as line
from scripts.publish_line_status import public_record


class DailyDateGuardTests(unittest.TestCase):
    def run_sender(self, *, quota_elapsed=0, retry_elapsed=0, unavailable=False):
        now = datetime(2026, 11, 27, 23, 59, 59, tzinfo=line.TAIPEI)
        clock = [100.0]
        report = {'date': '2026-11-27', 'edition': 'close', 'status': 'ready'}
        doc = {'close': report}
        if unavailable:
            doc['checks'] = {'close': {'date': '2026-11-27', 'status': 'pending'}}
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.headers = {'x-line-request-id': 'synthetic'}
        def quota(_token):
            clock[0] += quota_elapsed
            return True
        def pause(_seconds):
            clock[0] += retry_elapsed
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'remote').mkdir()
            (root / 'remote/brief.json').write_text(json.dumps(doc))
            result = root / 'result.json'
            effects = [TimeoutError('synthetic secret'), response] if retry_elapsed else [response]
            with patch.object(line, 'ROOT', root), patch.object(line, 'datetime') as dt, \
                 patch.object(line.time, 'monotonic', side_effect=lambda: clock[0]), \
                 patch.object(line.time, 'sleep', side_effect=pause), \
                 patch.object(line, 'quota_ok', side_effect=quota), \
                 patch.object(line.urllib.request, 'urlopen', side_effect=effects) as network, \
                 patch.dict(os.environ, {'JEI_LINE_ENABLED': 'true',
                     'JEI_LINE_CHANNEL_ACCESS_TOKEN': 'synthetic-token',
                     'JEI_LINE_USER_ID': 'U' + 'a' * 32}), \
                 patch.object(sys, 'argv', ['sender', '--edition', 'close', '--result-path', str(result)]):
                dt.now.return_value = now
                line.main()
            return json.loads(result.read_text()), network.call_count

    def test_quota_crossing_midnight_prevents_first_post(self):
        receipt, posts = self.run_sender(quota_elapsed=2)
        self.assertEqual(posts, 0)
        self.assertEqual(receipt['status'], 'blocked')
        self.assertEqual(receipt['reason_code'], 'dispatch_expired')
        self.assertFalse(receipt['delivery_confirmed'])

    def test_retry_crossing_midnight_preserves_attempt_but_stops_second_post(self):
        receipt, posts = self.run_sender(retry_elapsed=2)
        self.assertEqual(posts, 1)
        self.assertEqual(receipt['attempts'], 1)
        self.assertEqual(receipt['status'], 'blocked')
        self.assertNotIn('synthetic secret', json.dumps(receipt))

    def test_unavailable_notice_also_expires_at_midnight(self):
        receipt, posts = self.run_sender(quota_elapsed=2, unavailable=True)
        self.assertEqual(posts, 0)
        self.assertEqual(receipt['edition'], 'close_unavailable')
        self.assertEqual(receipt['status'], 'blocked')

    def test_same_date_still_accepts_without_claiming_delivery(self):
        receipt, posts = self.run_sender(quota_elapsed=0.2)
        self.assertEqual(posts, 1)
        self.assertEqual(receipt['status'], 'accepted')
        self.assertFalse(receipt['delivery_confirmed'])

    def test_public_daily_expiry_reason_is_allowlisted(self):
        for edition in ('morning', 'close', 'morning_unavailable', 'close_unavailable'):
            receipt = {'date': '2026-11-27', 'edition': edition,
                'checked_at': '2026-11-27T23:59:59+08:00', 'status': 'blocked',
                'reason_code': 'dispatch_expired', 'reason': 'synthetic secret'}
            row = public_record(receipt, '123', datetime(2026, 11, 28, tzinfo=line.TAIPEI))
            self.assertEqual(row.get('reason_code'), 'dispatch_expired')
            self.assertNotIn('synthetic secret', json.dumps(row))
