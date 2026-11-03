import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from scripts import send_line_alert as alert
from test_send_line_alert import feed, NOW

TOKEN='SENSITIVE_FAKE_TOKEN'
RECIPIENT='U'+'a'*32
class FixedDateTime(datetime):
    @classmethod
    def now(cls,tz=None): return NOW

class IntradayReceiptTests(unittest.TestCase):
    def run_main(self,document=None,environment=None,push=None,missing=False):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'feed.json';result=Path(temp)/'result.json'
            if not missing:source.write_text(json.dumps(feed() if document is None else document))
            env={'JEI_LINE_ALERTS_ENABLED':'true','JEI_LINE_ENABLED':'true','JEI_LINE_CHANNEL_ACCESS_TOKEN':TOKEN,'JEI_LINE_USER_ID':RECIPIENT}
            env.update(environment or {})
            stream=io.StringIO();exit_code=None
            with patch.dict(os.environ,env,clear=True),patch.object(alert,'FEED',source),patch.object(alert,'datetime',FixedDateTime),patch.object(alert,'push',side_effect=push) as send,contextlib.redirect_stdout(stream):
                try:alert.main(['--result-path',str(result)])
                except SystemExit as error:exit_code=error.code
            raw=result.read_text()
            for secret in (TOKEN,RECIPIENT,'PRIVATE_EXCEPTION_BODY'):
                self.assertNotIn(secret,raw)
                self.assertNotIn(secret,stream.getvalue())
                self.assertNotIn(secret,str(exit_code))
            receipt=json.loads(raw)
            self.assertIs(receipt['delivery_confirmed'],False)
            self.assertEqual(receipt['date'],NOW.date().isoformat())
            return receipt,send.call_count,exit_code

    def test_disabled_and_missing_credentials_write_distinct_receipts_without_push(self):
        for env,status,reason in [({'JEI_LINE_ALERTS_ENABLED':'false'},'disabled','alerts_disabled'),({'JEI_LINE_ENABLED':'false'},'blocked','master_switch_or_credentials'),({'JEI_LINE_CHANNEL_ACCESS_TOKEN':''},'blocked','master_switch_or_credentials')]:
            with self.subTest(env=env):
                r,c,e=self.run_main(environment=env)
                self.assertEqual((r['status'],r['reason_code'],c,e),(status,reason,0,None))

    def test_unreadable_or_invalid_shape_feed_never_pushes(self):
        r,c,e=self.run_main(missing=True)
        self.assertEqual((r['status'],r['reason_code'],c),('blocked','feed_unreadable',0))
        r,c,e=self.run_main(document=['PRIVATE_EXCEPTION_BODY'])
        self.assertEqual((r['status'],r['reason_code'],c),('blocked','live_gate',0))

    def test_stale_feed_has_explicit_gate_receipt(self):
        doc=feed();doc['data_date']='2026-10-19'
        r,c,e=self.run_main(document=doc)
        self.assertEqual((r['status'],r['reason_code'],c),('blocked','live_gate',0))

    def test_valid_feed_without_alert_does_not_call_push(self):
        doc=feed();doc['risk'].update(score=65,level='yellow')
        r,c,e=self.run_main(document=doc)
        self.assertEqual((r['status'],r['reason_code'],c,e),('no_alert','conditions_not_met',0,None))

    def test_acceptance_and_deduplication_never_claim_delivery(self):
        for status in ('accepted','already_accepted'):
            def push(*args,receipt):
                receipt.update(status=status,stage='push',attempts=1,http_status=200 if status=='accepted' else 409,request_id='fixture-request')
                return 'accepted'
            with self.subTest(status=status):
                r,c,e=self.run_main(push=push)
                self.assertEqual((r['status'],r['edition'],c,e),(status,'intraday_risk',1,None))

    def test_quota_blocked_is_recorded_and_not_reported_as_success(self):
        def push(*args,receipt):
            receipt.update(stage='quota',status='quota_blocked')
            return 'quota blocked'
        r,c,e=self.run_main(push=push)
        self.assertEqual((r['status'],r['stage'],c),('quota_blocked','quota',1))
        self.assertIsNotNone(e)

    def test_push_failure_is_sanitized_and_recorded(self):
        for failure in (OSError(TOKEN+' PRIVATE_EXCEPTION_BODY '+RECIPIENT),RuntimeError('PRIVATE_EXCEPTION_BODY')):
            with self.subTest(error=type(failure).__name__):
                r,c,e=self.run_main(push=failure)
                self.assertEqual((r['status'],r['error_type'],c),('failed',type(failure).__name__,1))
                self.assertIsNotNone(e)

    def test_malformed_risk_is_blocked_without_exception_or_push(self):
        doc=feed();doc['risk']='PRIVATE_EXCEPTION_BODY'
        r,c,e=self.run_main(document=doc)
        self.assertEqual((r['status'],r['reason_code'],c,e),('blocked','live_gate',0,None))

    def test_nonfinite_live_count_never_qualifies(self):
        for count in (float('nan'),float('inf'),float('-inf')):
            doc=feed();doc['market']['live_count']=count
            with self.subTest(count=count):self.assertFalse(alert.trusted_live(doc,NOW))

    def test_explicit_risk_stop_or_pick_stop_blocks_alert(self):
        for group,key in [('risk','actionable'),('market','no_new_picks')]:
            doc=feed();doc[group][key]=False if key=='actionable' else True
            with self.subTest(key=key):self.assertIsNone(alert.build_alert(doc,NOW))

    def test_nonfinite_momentum_values_cannot_be_notified(self):
        for key in ('score','change_pct','price'):
            for invalid in (float('inf'),float('nan')):
                doc=feed();doc['risk'].update(score=40,level='green')
                row={'code':'2330','name':'fixture','score':96,'change_pct':5,'price':100};row[key]=invalid
                doc['monster']=[row]
                with self.subTest(key=key,value=invalid):self.assertIsNone(alert.build_alert(doc,NOW))

if __name__=='__main__':unittest.main()
