import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from scripts.brief_dispatch_policy import select_policy

TZ=ZoneInfo('Asia/Taipei')
NOW=datetime(2026,11,5,19,6,tzinfo=TZ)
MESSAGE='verify(line): dispatch 2026-11-05 close with immutable outbox'

class BriefDispatchPolicyTests(unittest.TestCase):
    def select(self,**overrides):
        args=dict(event='push',schedule='',selected='',manual_send='false',head_message='',now=NOW)
        args.update(overrides)
        return select_policy(**args)

    def test_exact_one_day_verified_close_dispatch_can_run(self):
        self.assertEqual(self.select(head_message=MESSAGE),('close',True))

    def test_one_day_dispatch_expires_and_never_runs_before_close(self):
        for now in [NOW.replace(day=4),NOW.replace(day=6),NOW.replace(hour=8),NOW.replace(hour=13,minute=29)]:
            with self.subTest(now=now):self.assertEqual(self.select(head_message=MESSAGE,now=now),('close',False))

    def test_near_match_and_unrelated_pushes_never_send(self):
        for message in ['',MESSAGE+' extra','fix(line): dispatch close','verify(line): dispatch 2026-11-06 close with immutable outbox']:
            with self.subTest(message=message):self.assertEqual(self.select(head_message=message),('close',False))

    def test_commit_override_requires_push_event(self):
        self.assertEqual(self.select(event='pull_request',head_message=MESSAGE),('close',False))

    def test_existing_schedules_keep_editions_and_send_policy(self):
        for cron in ['55 0 * * 1-5','10 1 * * 1-5','25 1 * * 1-5']:
            self.assertEqual(self.select(event='schedule',schedule=cron),('morning',True))
        for cron in ['10 10 * * 1-5','40 10 * * 1-5','10 11 * * 1-5']:
            self.assertEqual(self.select(event='schedule',schedule=cron),('close',True))
        self.assertEqual(self.select(event='schedule',schedule='30 7 * * 1-5'),('close',False))

    def test_unknown_schedule_and_spoofed_manual_value_do_not_send(self):
        self.assertEqual(self.select(event='schedule',schedule='unknown',manual_send='true'),('close',False))
        self.assertEqual(self.select(schedule='10 10 * * 1-5',manual_send='true'),('close',False))

    def test_existing_manual_dispatch_requires_explicit_true(self):
        self.assertEqual(self.select(event='workflow_dispatch',selected='morning',manual_send='true'),('morning',True))
        self.assertEqual(self.select(event='workflow_dispatch',selected='morning',manual_send='false'),('morning',False))

    def test_invalid_edition_is_rejected(self):
        with self.assertRaises(ValueError):self.select(selected='secret')

    def test_missing_timezone_is_rejected(self):
        with self.assertRaises(ValueError):self.select(head_message=MESSAGE,now=NOW.replace(tzinfo=None))
