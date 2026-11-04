"""Public LINE diagnostics must preserve evidence without exposing recipients."""
import copy
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.publish_line_status import merge_status

NOW = datetime(2026, 11, 5, 1, 0, tzinfo=ZoneInfo('Asia/Taipei'))


def receipt(**changes):
    return {'date': '2026-11-04', 'edition': 'close',
            'checked_at': '2026-11-04T19:15:51+08:00', 'status': 'accepted',
            'http_status': 200, 'attempts': 1, **changes}


class LineStatusTests(unittest.TestCase):
    def test_acceptance_never_claims_phone_delivery_or_copies_private_fields(self):
        original = receipt(delivery_confirmed=True, to='U'+'a'*32, token='SECRET',
                           request_id='PRIVATE_ID', reason='SECRET', payload={'cost': 100})
        before = copy.deepcopy(original)
        result = merge_status({}, original, '41819662980', NOW)
        row = result['editions']['close']
        self.assertTrue(row['api_accepted'])
        self.assertFalse(row['delivery_confirmed'])
        self.assertEqual(row['evidence_url'], 'https://github.com/alwaysjei1234-sys/JEI-Stock-Radar/actions/runs/41819662980')
        for value in ('SECRET', 'PRIVATE_ID', 'a'*32, 'payload', 'cost'):
            self.assertNotIn(value, str(result))
        self.assertEqual(original, before)

    def test_duplicate_is_distinct_from_a_new_acceptance(self):
        row = merge_status({}, receipt(status='already_accepted', http_status=409), '123', NOW)['editions']['close']
        self.assertEqual(row['status'], 'already_accepted')
        self.assertTrue(row['api_accepted'])
        self.assertFalse(row['delivery_confirmed'])

    def test_failure_and_quota_block_remain_visible_without_acceptance(self):
        for status in ('blocked', 'failed', 'quota_blocked'):
            with self.subTest(status=status):
                row = merge_status({}, receipt(status=status, http_status=401), '123', NOW)['editions']['close']
                self.assertFalse(row['api_accepted'])
                self.assertEqual(row['status'], status)

    def test_notice_preserves_its_edition_instead_of_claiming_a_market_report(self):
        row = merge_status({}, receipt(edition='close_unavailable'), '123', NOW)['editions']['close']
        self.assertEqual(row['edition'], 'close_unavailable')

    def test_invalid_or_future_evidence_is_rejected(self):
        for change in ({'checked_at': '2026-11-05T01:03:00+08:00', 'date': '2026-11-05'},
                       {'checked_at': '2026-11-04T19:15:51'}, {'date': '2026-11-03'},
                       {'http_status': 500}, {'http_status': True}, {'edition': 'test'},
                       {'status': 'delivered'}, {'checked_at': 'malformed'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                merge_status({}, receipt(**change), '123', NOW)
        with self.assertRaises(ValueError):
            merge_status({}, receipt(), 'https://evil.example', NOW)

    def test_old_completion_cannot_overwrite_newer_status_and_other_edition_survives(self):
        prior = merge_status({}, receipt(checked_at='2026-11-04T19:56:20+08:00', status='already_accepted', http_status=409), '124', NOW)
        prior = merge_status(prior, receipt(edition='morning', checked_at='2026-11-04T09:15:00+08:00'), '125', NOW)
        result = merge_status(prior, receipt(), '123', NOW)
        self.assertEqual(result['editions']['close']['evidence_url'].rsplit('/', 1)[1], '124')
        self.assertIn('morning', result['editions'])
        self.assertEqual(result['updated_at'], '2026-11-04T19:56:20+08:00')

    def test_existing_unknown_fields_are_not_republished(self):
        prior = merge_status({}, receipt(), '123', NOW)
        prior['secret'] = 'SECRET'
        prior['editions']['close']['token'] = 'SECRET'
        result = merge_status(prior, receipt(edition='morning', checked_at='2026-11-04T09:15:00+08:00'), '124', NOW)
        self.assertNotIn('SECRET', str(result))

    def test_later_failed_backup_preserves_acceptance_and_latest_decision(self):
        for status in ('quota_blocked', 'failed', 'blocked'):
            with self.subTest(status=status):
                prior = merge_status({}, receipt(), '123', NOW)
                later = receipt(status=status, http_status=429,
                                checked_at='2026-11-04T19:56:20+08:00')
                row = merge_status(prior, later, '124', NOW)['editions']['close']
                self.assertEqual(row['status'], status)
                self.assertFalse(row['api_accepted'])
                self.assertEqual(row['accepted_attempt']['evidence_url'].rsplit('/', 1)[1], '123')
                self.assertFalse(row['accepted_attempt']['delivery_confirmed'])
                row['accepted_attempt']['token'] = 'SECRET'
                again = merge_status({'editions': {'close': row}}, later, '124', NOW)
                self.assertNotIn('SECRET', str(again))
                self.assertIn('accepted_attempt', again['editions']['close'])

    def test_late_older_accepted_run_is_kept_beside_newer_failure(self):
        prior = merge_status({}, receipt(status='failed', http_status=500,
                            checked_at='2026-11-04T19:56:20+08:00'), '124', NOW)
        row = merge_status(prior, receipt(), '123', NOW)['editions']['close']
        self.assertEqual(row['status'], 'failed')
        self.assertEqual(row['accepted_attempt']['checked_at'], receipt()['checked_at'])

    def test_acceptance_is_not_reused_for_new_day_or_different_notice_edition(self):
        prior = merge_status({}, receipt(edition='close_unavailable'), '123', NOW)
        row = merge_status(prior, receipt(status='failed', http_status=500,
                           checked_at='2026-11-04T19:56:20+08:00'), '124', NOW)['editions']['close']
        self.assertNotIn('accepted_attempt', row)
        prior = merge_status({}, receipt(), '123', NOW)
        row = merge_status(prior, receipt(date='2026-11-05', status='failed', http_status=500,
                           checked_at='2026-11-05T00:30:00+08:00'), '124', NOW)['editions']['close']
        self.assertNotIn('accepted_attempt', row)

    def test_forged_nested_acceptance_is_discarded(self):
        for changes in ({'http_status': 500}, {'date': '2026-11-03'},
                        {'checked_at': '2026-11-05T01:03:00+08:00'},
                        {'evidence_url': 'https://evil.example/123'}, {'status': 'delivered'}):
            with self.subTest(changes=changes):
                prior = merge_status({}, receipt(status='failed', http_status=500), '124', NOW)
                nested = merge_status({}, receipt(), '123', NOW)['editions']['close']
                prior['editions']['close']['accepted_attempt'] = {**nested, **changes}
                row = merge_status(prior, receipt(edition='morning',
                                   checked_at='2026-11-04T09:15:00+08:00'), '125', NOW)['editions']['close']
                self.assertNotIn('accepted_attempt', row)

    def test_workflow_recovers_from_a_real_push_race_without_losing_market_data(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root/'.github/workflows/jei-daily-brief.yml').read_text()
        block = workflow.split('      - name: Publish public LINE decision without recipient or credentials\n', 1)[1]
        script = '\n'.join(line[10:] for line in block.split('        run: |\n', 1)[1].splitlines())
        real_git = shutil.which('git')
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            bare, work, competitor = (base/name for name in ('remote.git', 'work', 'competitor'))
            def git(*args, cwd=None):
                return subprocess.run([real_git, *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()
            git('init', '--bare', str(bare))
            git('init', '-b', 'main', str(work))
            git('config', 'user.name', 'Fixture', cwd=work)
            git('config', 'user.email', 'fixture@example.invalid', cwd=work)
            (work/'scripts').mkdir(); (work/'remote').mkdir()
            shutil.copy(root/'scripts/publish_line_status.py', work/'scripts')
            (work/'remote/line_status.json').write_text('{}')
            (work/'remote/system.json').write_text('{"marker":"old"}')
            git('add', '.', cwd=work); git('commit', '-m', 'initial', cwd=work)
            git('remote', 'add', 'origin', str(bare), cwd=work)
            git('push', '-u', 'origin', 'main', cwd=work)
            git('clone', '-b', 'main', str(bare), str(competitor))
            git('config', 'user.name', 'Fixture', cwd=competitor)
            git('config', 'user.email', 'fixture@example.invalid', cwd=competitor)
            morning = merge_status({}, receipt(edition='morning', checked_at='2026-11-04T09:15:00+08:00'), '125', NOW)
            (competitor/'remote/line_status.json').write_text(json.dumps(morning))
            (competitor/'remote/system.json').write_text('{"marker":"new-main"}')
            git('add', '.', cwd=competitor); git('commit', '-m', 'concurrent market update', cwd=competitor)
            raw = base/'receipt.json'; raw.write_text(json.dumps(receipt()))
            bin_path = base/'bin'; bin_path.mkdir()
            wrapper = bin_path/'git'
            wrapper.write_text('#!/usr/bin/env python3\nimport os,subprocess,sys\nfrom pathlib import Path\n'
                'marker=Path(os.environ["RACE_MARKER"])\n'
                'if sys.argv[1:]==["push"] and not marker.exists():\n'
                ' subprocess.run([os.environ["REAL_GIT"],"-C",os.environ["COMPETITOR"],"push"],check=True)\n'
                ' marker.touch()\n'
                'os.execv(os.environ["REAL_GIT"],[os.environ["REAL_GIT"],*sys.argv[1:]])\n')
            wrapper.chmod(0o755)
            result = subprocess.run(['bash', '-eo', 'pipefail', '-c', script], cwd=work, capture_output=True, text=True,
                env={**os.environ, 'PATH':str(bin_path)+os.pathsep+os.environ['PATH'], 'REAL_GIT':real_git,
                     'RACE_MARKER':str(base/'raced'), 'COMPETITOR':str(competitor),
                     'LINE_RECEIPT_PATH':str(raw), 'LINE_RUN_ID':'123'})
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertTrue((base/'raced').exists())
            self.assertEqual(json.loads((work/'remote/system.json').read_text())['marker'], 'new-main')
            merged = json.loads((work/'remote/line_status.json').read_text())
            self.assertEqual(set(merged['editions']), {'morning', 'close'})
            self.assertEqual(git('rev-parse', 'HEAD', cwd=work), git('rev-parse', 'refs/heads/main', cwd=bare))


if __name__ == '__main__':
    unittest.main()
