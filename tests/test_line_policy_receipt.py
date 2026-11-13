import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from scripts.brief_dispatch_policy import record_pre_send_failure, skipped_receipt, TAIPEI
from scripts.publish_line_status import merge_status, merge_policy_status, RUN_BASE


class LinePolicyReceiptTests(unittest.TestCase):
    now=datetime(2026,11,11,2,37,55,tzinfo=TAIPEI)

    def policy(self):
        return skipped_receipt('schedule','10 11 * * 1-5',self.now)

    def test_observed_delayed_close_is_not_an_api_attempt_and_does_not_replace_acceptance(self):
        prior={'date':'2026-11-10','edition':'close','checked_at':'2026-11-10T19:10:00+08:00',
               'status':'accepted','http_status':200}
        document=merge_status({},prior,'123',self.now);old=copy.deepcopy(document['editions'])
        result=merge_policy_status(document,self.policy(),'42877121927',self.now)
        self.assertEqual(result['editions'],old)
        check=result['policy_checks']['close']
        self.assertEqual(check['date'],'2026-11-11')
        self.assertEqual(check['policy_code'],'dispatch_window_not_open')
        self.assertFalse(check['api_accepted']);self.assertFalse(check['delivery_confirmed'])
        self.assertEqual(check['evidence_url'],RUN_BASE+'42877121927')
        self.assertNotIn('http_status',check)

    def test_routine_builds_manual_builds_unknown_and_eligible_schedules_do_not_record_skips(self):
        for event,cron,now in [('push','10 11 * * 1-5',self.now),
                ('workflow_dispatch','10 11 * * 1-5',self.now),
                ('schedule','30 7 * * 1-5',self.now),('schedule','unknown',self.now),
                ('schedule','10 11 * * 1-5',self.now.replace(hour=20))]:
            self.assertIsNone(skipped_receipt(event,cron,now))

    def test_upstream_failure_is_preserved_as_no_send_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            record_pre_send_failure("close", path, self.now)
            policy = json.loads(path.read_text())
            record_pre_send_failure("morning", path, self.now)
            self.assertEqual(json.loads(path.read_text()), policy)
        result = merge_policy_status({}, policy, "123", self.now)
        check = result["policy_checks"]["close"]
        self.assertEqual(check["policy_code"], "brief_failed_before_send")
        self.assertFalse(check["api_accepted"])
        self.assertNotIn("http_status", check)
        self.assertEqual(result["editions"], {})

    def test_private_fields_and_forged_acceptance_are_never_published(self):
        receipt=self.policy()|{'token':'SECRET','to':'PRIVATE','api_accepted':True,
                              'delivery_confirmed':True,'reason':'SECRET','http_status':200}
        result=merge_policy_status({},receipt,'123',self.now)
        self.assertNotIn('SECRET',json.dumps(result));self.assertNotIn('PRIVATE',json.dumps(result))
        self.assertFalse(result['policy_checks']['close']['api_accepted'])
        bad=self.policy()|{'policy_code':'SECRET'}
        with self.assertRaises(ValueError):merge_policy_status({},bad,'123',self.now)

    def test_newer_policy_survives_old_arrivals_and_later_api_attempts(self):
        result=merge_policy_status({},self.policy(),'123',self.now)
        earlier=self.policy()|{'checked_at':'2026-11-11T01:00:00+08:00'}
        result=merge_policy_status(result,earlier,'122',self.now)
        self.assertEqual(result['policy_checks']['close']['evidence_url'],RUN_BASE+'123')
        api={'date':'2026-11-11','edition':'close','checked_at':self.now.isoformat(),
             'status':'quota_blocked'}
        result=merge_status(result,api,'124',self.now)
        self.assertEqual(result['policy_checks']['close']['evidence_url'],RUN_BASE+'123')

    def test_repeated_same_day_reason_is_idempotent_to_avoid_redundant_publications(self):
        result=merge_policy_status({},self.policy(),'123',self.now)
        later=self.policy()|{'checked_at':'2026-11-11T03:00:00+08:00'}
        self.assertEqual(merge_policy_status(result,later,'124',self.now.replace(hour=4)),result)

    def test_cli_generates_and_publishes_sanitized_policy_without_network_or_secrets(self):
        # Exercise both real CLIs; an early close slot always skips on this date.
        from unittest.mock import patch
        import scripts.brief_dispatch_policy as policy
        with tempfile.TemporaryDirectory() as temp:
            receipt=Path(temp)/'receipt.json';output=Path(temp)/'status.json'
            with patch.object(policy,'datetime') as clock,patch.dict(os.environ,{
                    'EVENT':'schedule','SCHEDULE':'10 11 * * 1-5','SELECTED':'close',
                    'MANUAL_SEND':'false','LINE_POLICY_RECEIPT_PATH':str(receipt)}):
                clock.now.return_value=self.now
                policy.main()
            subprocess.run([sys.executable,'scripts/publish_line_status.py','--receipt',str(receipt),
                            '--run-id','42877121927','--output',str(output)],check=True,
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            record=json.loads(output.read_text())
            self.assertEqual(record['editions'],{})
            self.assertEqual(record['policy_checks']['close']['status'],'policy_skipped')
