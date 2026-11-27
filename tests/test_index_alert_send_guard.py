"""Exercise real siren -> LINE sender with fake transport; never send a message."""
import contextlib
from datetime import datetime
import io
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from scripts import early_index_crash_alert as siren
from scripts import send_line_brief as sender


class Clock:
    value=0
    def now(self):return self.value
    def sleep(self,seconds):self.value+=seconds


class Accepted(io.BytesIO):
    status=200
    headers={}


class IndexSendGuardTests(unittest.TestCase):
    def exercise(self, at, stamp, quota_delay=0, retry=False):
        clock=Clock()
        quote=dict(c='t00',ex='tse',ch='t00.tw',d='20261127',
                   t=stamp,z='970',y='1000')
        receipt={'status':'failed','delivery_confirmed':False}
        def quota(*args):clock.value+=quota_delay;return True
        requests=[]
        def transport(request,**kwargs):
            requests.append(request)
            if retry and len(requests)==1:
                raise HTTPError(sender.PUSH,503,'synthetic unavailable',{},None)
            return Accepted()
        env={'JEI_LINE_ENABLED':'true','JEI_LINE_ALERTS_ENABLED':'true',
             'JEI_LINE_CHANNEL_ACCESS_TOKEN':'SYNTHETIC_TOKEN',
             'JEI_LINE_USER_ID':'U'+'a'*32}
        with patch.dict(os.environ,env,clear=True),patch.object(siren,'fetch_mis_channels',return_value=[quote]),patch.object(
                sender,'quota_ok',side_effect=quota),patch.object(sender.time,'monotonic',clock.now),patch.object(
                sender.time,'sleep',clock.sleep),patch.object(sender.urllib.request,'urlopen',side_effect=transport),contextlib.redirect_stdout(io.StringIO()):
            siren.dispatch(at,receipt)
        return receipt,requests

    def test_quota_delay_crossing_close_prevents_first_post(self):
        at=datetime(2026,11,27,13,29,58,tzinfo=sender.TAIPEI)
        receipt,requests=self.exercise(at,'13:29:57',quota_delay=3)
        self.assertEqual(len(requests),0)
        self.assertEqual((receipt['status'],receipt['reason_code']),('blocked','dispatch_expired'))
        self.assertFalse(receipt['delivery_confirmed'])

    def test_quota_delay_expiring_quote_prevents_first_post(self):
        at=datetime(2026,11,27,10,0,tzinfo=sender.TAIPEI)
        receipt,requests=self.exercise(at,'09:50:05',quota_delay=8)
        self.assertEqual(len(requests),0)
        self.assertEqual((receipt['status'],receipt['reason_code']),('blocked','dispatch_expired'))

    def test_retry_backoff_crossing_close_prevents_next_post(self):
        at=datetime(2026,11,27,13,29,59,tzinfo=sender.TAIPEI)
        receipt,requests=self.exercise(at,'13:29:57',retry=True)
        self.assertEqual(len(requests),1)
        self.assertEqual((receipt['status'],receipt['reason_code']),('blocked','dispatch_expired'))
        self.assertEqual(receipt['attempts'],1)
        self.assertEqual(receipt['http_status'],503)

    def test_still_valid_siren_keeps_api_acceptance_and_no_device_claim(self):
        at=datetime(2026,11,27,10,0,tzinfo=sender.TAIPEI)
        receipt,requests=self.exercise(at,'09:59:00',quota_delay=3)
        self.assertEqual(len(requests),1)
        self.assertEqual((receipt['status'],receipt['http_status']),('accepted',200))
        self.assertFalse(receipt['delivery_confirmed'])
        self.assertEqual(requests[0].method,'POST')

    def test_public_receipt_preserves_only_matching_expiry_reason(self):
        from scripts.publish_line_status import public_record, INDEX_EDITIONS
        at=datetime(2026,11,27,13,29,58,tzinfo=sender.TAIPEI)
        receipt,_=self.exercise(at,'13:29:57',quota_delay=3)
        for edition in INDEX_EDITIONS:
            item={**receipt,'date':'2026-11-27','checked_at':at.isoformat(),
                  'edition':edition,'token':'SYNTHETIC_PRIVATE'}
            row=public_record(item,'123',at)
            self.assertEqual(row.get('reason_code'),'dispatch_expired')
            self.assertFalse(row['api_accepted'])
            self.assertFalse(row['delivery_confirmed'])
            self.assertNotIn('SYNTHETIC_PRIVATE',str(row))
            row=public_record({**item,'status':'accepted','http_status':200},'123',at)
            self.assertNotIn('reason_code',row)
