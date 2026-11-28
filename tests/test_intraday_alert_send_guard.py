"""Real intraday dispatcher and sender, synthetic clock/transport only."""
import contextlib
from datetime import datetime
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from scripts import send_line_alert as alert
from scripts import send_line_brief as sender


class Accepted(io.BytesIO):
    status = 200
    headers = {}


class IntradaySendGuardTests(unittest.TestCase):
    def exercise(self, at, stamp, *, momentum=False, quota_delay=0, retry=False):
        elapsed = [0]
        feed = {'data_date':'2026-11-27', 'updated_at':'2026-11-27 '+stamp,
                'market':{'mode':'盤中即時','stale':False,'live_valid':True,
                          'live_count':700,'close_count':2000},
                'risk':{'as_of':'2026-11-27','level':'red','score':85}}
        if momentum:
            feed['risk'].update(level='green',score=30)
            feed['monster'] = [{'code':'2330','name':'合成測試','score':96,
                                'change_pct':5,'price':100}]
        receipt = {'date':'2026-11-27','checked_at':at.isoformat(),
                   'status':'failed','delivery_confirmed':False}
        requests = []
        def quota(*args):
            elapsed[0] += quota_delay
            return True
        def transport(request, **kwargs):
            requests.append(request)
            if retry and len(requests) == 1:
                raise HTTPError(sender.PUSH,503,'synthetic unavailable',{},None)
            return Accepted()
        def sleep(seconds):
            elapsed[0] += seconds
        env = {'JEI_LINE_ENABLED':'true','JEI_LINE_ALERTS_ENABLED':'true',
               'JEI_LINE_CHANNEL_ACCESS_TOKEN':'SYNTHETIC_TOKEN',
               'JEI_LINE_USER_ID':'U'+'a'*32}
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'feed.json'; source.write_text(json.dumps(feed))
            with patch.dict(os.environ,env,clear=True), patch.object(alert,'FEED',source), \
                 patch('time.monotonic',side_effect=lambda:elapsed[0]), \
                 patch.object(sender,'quota_ok',side_effect=quota), \
                 patch.object(sender.time,'sleep',side_effect=sleep), \
                 patch.object(sender.urllib.request,'urlopen',side_effect=transport), \
                 contextlib.redirect_stdout(io.StringIO()):
                alert.dispatch(at,receipt)
        return receipt, requests

    def test_quota_delay_crossing_close_prevents_first_post(self):
        at = datetime(2026,11,27,13,29,58,tzinfo=sender.TAIPEI)
        for momentum in (False,True):
            with self.subTest(momentum=momentum):
                receipt, requests = self.exercise(at,'13:29',momentum=momentum,quota_delay=3)
                self.assertEqual(len(requests),0)
                self.assertEqual(receipt.get('reason_code'),'dispatch_expired')

    def test_quota_delay_expiring_snapshot_prevents_first_post(self):
        at = datetime(2026,11,27,10,0,tzinfo=sender.TAIPEI)
        receipt, requests = self.exercise(at,'09:50',quota_delay=1)
        self.assertEqual(len(requests),0)
        self.assertEqual(receipt.get('reason_code'),'dispatch_expired')

    def test_retry_backoff_crossing_close_preserves_first_attempt(self):
        at = datetime(2026,11,27,13,29,59,tzinfo=sender.TAIPEI)
        receipt, requests = self.exercise(at,'13:29',retry=True)
        self.assertEqual(len(requests),1)
        self.assertEqual((receipt['attempts'],receipt['http_status']),(1,503))
        self.assertEqual(receipt.get('reason_code'),'dispatch_expired')

    def test_still_valid_alert_acceptance_never_claims_device_delivery(self):
        at = datetime(2026,11,27,10,0,tzinfo=sender.TAIPEI)
        for momentum in (False,True):
            with self.subTest(momentum=momentum):
                receipt, requests = self.exercise(at,'09:59',momentum=momentum,quota_delay=3)
                self.assertEqual(len(requests),1)
                self.assertEqual((receipt['status'],receipt['http_status']),('accepted',200))
                self.assertFalse(receipt['delivery_confirmed'])

    def test_public_expiry_reason_is_allowlisted_only_for_blocked_receipt(self):
        from scripts.publish_line_status import public_record
        at = datetime(2026,11,27,13,29,58,tzinfo=sender.TAIPEI)
        for edition in ('intraday_risk','intraday_momentum'):
            row = {'date':'2026-11-27','checked_at':at.isoformat(),'edition':edition,
                   'status':'blocked','reason_code':'dispatch_expired','token':'SYNTHETIC_PRIVATE'}
            clean = public_record(row,'123',at)
            self.assertEqual(clean.get('reason_code'),'dispatch_expired')
            self.assertFalse(clean['api_accepted'])
            self.assertFalse(clean['delivery_confirmed'])
            self.assertNotIn('SYNTHETIC_PRIVATE',str(clean))
            clean = public_record({**row,'status':'accepted','http_status':200},'123',at)
            self.assertNotIn('reason_code',clean)
