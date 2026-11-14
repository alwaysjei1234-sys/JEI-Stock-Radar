import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from scripts import verify_line_push as test_push


class VerifyLinePushTests(unittest.TestCase):
    now = datetime(2026, 11, 10, 22, tzinfo=test_push.line.TAIPEI)
    token = 'PRIVATE_TOKEN'
    recipient = 'U'+'a'*32

    def verify(self, **kwargs):
        return test_push.verify(kwargs.get('day','2026-11-10'), self.now,
                                kwargs.get('enabled','true'), self.token, self.recipient)

    def test_automated_push_trigger_requires_the_exact_dated_commit(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/jei-line-test.yml").read_text()
        self.assertNotIn("startsWith", workflow)
        self.assertIn(
            "github.event.head_commit.message == 'test(line): verify live delivery 2026-11-14'",
            workflow,
        )
        self.assertIn("inputs.expected_day || '2026-11-14'", workflow)

    def test_expired_or_missing_date_and_disabled_configuration_never_send(self):
        with patch.object(test_push.line, 'push') as send:
            for day in ('', '2026-11-09', '2026-11-11'):
                self.assertEqual(self.verify(day=day)['reason'], 'test_date_mismatch')
            self.assertEqual(self.verify(enabled='false')['status'], 'blocked')
            send.assert_not_called()

    def test_real_sender_acceptance_and_deduplication_never_confirm_phone(self):
        response = MagicMock(); response.__enter__.return_value = response
        response.status = 200; response.headers = {'x-line-request-id':'PRIVATE_ID'}
        duplicate = HTTPError(test_push.line.PUSH,409,'PRIVATE',
                              {'x-line-accepted-request-id':'PRIVATE_ID'},None)
        with patch.object(test_push.line,'quota_ok',return_value=True), patch.object(
                test_push.line.urllib.request,'urlopen',side_effect=[response,duplicate]) as network:
            accepted, repeated = self.verify(), self.verify()
        self.assertEqual(accepted['status'],'accepted')
        self.assertEqual(repeated['status'],'already_accepted')
        requests=[call.args[0] for call in network.call_args_list]
        self.assertEqual(requests[0].get_header('X-line-retry-key'),requests[1].get_header('X-line-retry-key'))
        self.assertEqual(requests[0].data,requests[1].data)
        for result in (accepted,repeated):
            self.assertTrue(result['api_accepted'])
            self.assertFalse(result['delivery_confirmed'])
            for private in (self.token,self.recipient,'PRIVATE_ID'):
                self.assertNotIn(private,json.dumps(result))

    def test_quota_failure_does_not_send_or_claim_acceptance(self):
        with patch.object(test_push.line,'quota_ok',return_value=False), patch.object(
                test_push.line.urllib.request,'urlopen') as network:
            result=self.verify()
        network.assert_not_called()
        self.assertEqual(result['status'],'quota_blocked')
        self.assertFalse(result['api_accepted'])

    def test_transport_failure_is_bounded_and_error_text_is_not_published(self):
        with patch.object(test_push.line,'quota_ok',return_value=True), patch.object(
                test_push.line.urllib.request,'urlopen',side_effect=OSError('PRIVATE_TOKEN')), patch.object(
                test_push.line.time,'sleep'):
            result=self.verify()
        self.assertEqual(result['attempts'],3)
        self.assertFalse(result['api_accepted'])
        self.assertNotIn('PRIVATE',json.dumps(result))
