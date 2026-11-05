"""Persist public message bytes before cross-process retries, without recipients."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
from zoneinfo import ZoneInfo
from scripts import line_outbox as outbox
from scripts import send_line_brief as sender

NOW = datetime(2026, 11, 5, 18, 10, tzinfo=ZoneInfo('Asia/Taipei'))
REPORT = {'date': '2026-11-05', 'edition': 'close', 'status': 'ready', 'title': 'original close'}


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'outbox.json'

    def freeze(self, report=None, status=None):
        return outbox.freeze({'close': report or REPORT}, 'close', NOW, self.path, status or {})

    def test_first_freeze_is_public_and_reloading_preserves_original_message(self):
        self.freeze()
        original = self.path.read_bytes()
        self.freeze({**REPORT, 'title': 'a newer regenerated report'})
        self.assertEqual(self.path.read_bytes(), original)
        body = outbox.load(self.path, '2026-11-05', 'close')
        self.assertIn('original close', body['messages'][0]['text'])
        self.assertNotIn('to', body)
        self.assertEqual(set(body), {'messages', 'notificationDisabled'})

    def test_retry_requests_keep_identical_body_and_key_after_report_refresh(self):
        self.freeze()
        requests = []
        response = MagicMock(); response.__enter__.return_value = response
        response.status = 200; response.headers = {'x-line-request-id': 'test'}
        def capture(request, timeout):
            requests.append(request)
            return response
        with patch.object(sender, 'quota_ok', return_value=True), patch.object(sender.urllib.request, 'urlopen', side_effect=capture):
            for title in ['first process', 'backup process']:
                frozen = outbox.load(self.path, REPORT['date'], 'close')
                sender.push({**REPORT, 'title': title}, 'close', 'secret-token', 'U'+'a'*32,
                            message_payload=frozen)
        self.assertEqual(requests[0].data, requests[1].data)
        self.assertEqual(requests[0].get_header('X-line-retry-key'), requests[1].get_header('X-line-retry-key'))
        self.assertNotIn('secret-token', self.path.read_text())
        self.assertNotIn('U'+'a'*32, self.path.read_text())

    def test_legacy_acceptance_without_original_body_blocks_reconstruction(self):
        status = {'editions': {'close': {**REPORT, 'status': 'accepted', 'api_accepted': True}}}
        with self.assertRaises(ValueError): self.freeze(status=status)
        self.assertFalse(self.path.exists())

    def test_legacy_unavailable_notice_does_not_block_recovered_verified_report(self):
        status = {'editions': {'close': {**REPORT, 'edition': 'close_unavailable', 'status': 'accepted', 'api_accepted': True}}}
        self.freeze(status=status)
        self.assertTrue(self.path.exists())

    def test_pending_notice_and_recovery_have_separate_immutable_slots(self):
        pending = {'checks': {'close': {'date': REPORT['date'], 'status': 'pending', 'note': 'not ready'}}}
        outbox.freeze(pending, 'close', NOW, self.path, {})
        self.freeze()
        notice = outbox.load(self.path, REPORT['date'], 'close_unavailable')
        report = outbox.load(self.path, REPORT['date'], 'close')
        self.assertNotEqual(notice, report)

    def test_old_or_unready_report_is_never_frozen(self):
        for report in [{**REPORT, 'date': '2026-11-04'}, {**REPORT, 'status': 'pending'}]:
            with self.subTest(report=report), self.assertRaises(ValueError): self.freeze(report)
        self.assertFalse(self.path.exists())

    def test_corrupt_existing_file_is_not_overwritten(self):
        self.path.write_text('not json')
        with self.assertRaises(ValueError): self.freeze()
        self.assertEqual(self.path.read_text(), 'not json')

    def test_missing_slot_and_injected_recipient_are_rejected(self):
        self.freeze()
        with self.assertRaises(ValueError): outbox.load(self.path, '2026-11-06', 'close')
        doc = json.loads(self.path.read_text())
        doc['records']['2026-11-05/close']['payload']['to'] = 'PRIVATE'
        self.path.write_text(json.dumps(doc))
        with self.assertRaises(ValueError): outbox.load(self.path, '2026-11-05', 'close')

    def test_existing_snapshot_survives_newer_legacy_status(self):
        self.freeze()
        original = self.path.read_bytes()
        self.freeze(status={'editions': {'close': {**REPORT, 'status': 'already_accepted', 'api_accepted': True}}})
        self.assertEqual(self.path.read_bytes(), original)
