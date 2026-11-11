"""Exercise the workflow's actual publish shell against local competing Git writers."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/jei-daily-brief.yml'


def git(root, *args, check=True):
    return subprocess.run(['git', *args], cwd=root, check=check,
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class BriefPublicationRaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.remote = self.base / 'origin.git'
        self.worker = self.base / 'worker'
        self.peer = self.base / 'peer'
        git(self.base, 'init', '--bare', '--initial-branch=main', str(self.remote))
        git(self.base, 'clone', str(self.remote), str(self.worker))
        for key, value in [('user.name', 'test'), ('user.email', 'test@example.invalid')]:
            git(self.worker, 'config', key, value)
        (self.worker / 'remote').mkdir()
        (self.worker / 'scripts').mkdir()
        (self.worker / 'remote/brief.json').write_text(json.dumps({'morning': 'original', 'close': 'old'}))
        (self.worker / 'remote/system.json').write_text(json.dumps({'revision': 'old'}))
        # A deterministic stand-in for the separately-tested report builder.
        # Crucially it merges the newest other edition and reads the newest feed.
        (self.worker / 'scripts/build_daily_brief.py').write_text(textwrap.dedent('''
            import json
            from pathlib import Path
            brief = Path('remote/brief.json')
            doc = json.loads(brief.read_text())
            doc['close'] = json.loads(Path('remote/system.json').read_text())['revision']
            brief.write_text(json.dumps(doc))
        '''))
        git(self.worker, 'add', '.')
        git(self.worker, 'commit', '-m', 'initial')
        git(self.worker, 'push', '-u', 'origin', 'main')
        git(self.base, 'clone', str(self.remote), str(self.peer))
        for key, value in [('user.name', 'peer'), ('user.email', 'peer@example.invalid')]:
            git(self.peer, 'config', key, value)

    def publish(self, send=False):
        workflow = WORKFLOW.read_text()
        block = workflow.split('      - name: Publish verified report\n', 1)[1].split('        run: |\n', 1)[1].split('      - name:', 1)[0]
        shell = textwrap.dedent(block).replace('${{ steps.edition.outputs.name }}', 'close').replace('${{ steps.edition.outputs.send }}', 'true' if send else 'false')
        # sleep is not part of the behavior under test.
        shell = shell.replace('sleep 3', ':')
        return subprocess.run(['bash', '-e', '-c', shell], cwd=self.worker,
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})

    def test_competing_brief_is_regenerated_without_losing_new_feed_or_other_edition(self):
        (self.worker / 'remote/brief.json').write_text(json.dumps({'morning': 'original', 'close': 'worker'}))
        (self.peer / 'remote/brief.json').write_text(json.dumps({'morning': 'new morning', 'close': 'peer'}))
        (self.peer / 'remote/system.json').write_text(json.dumps({'revision': 'new feed'}))
        git(self.peer, 'add', '.')
        git(self.peer, 'commit', '-m', 'concurrent reports and market')
        git(self.peer, 'push')
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        actual = json.loads(git(self.base, '--git-dir='+str(self.remote), 'show', 'main:remote/brief.json').stdout)
        self.assertEqual(actual, {'morning': 'new morning', 'close': 'new feed'})
        self.assertEqual(git(self.worker, 'status', '--porcelain').stdout, '')
        self.assertFalse((self.worker / '.git/rebase-merge').exists())

    def test_unchanged_report_does_not_make_a_commit(self):
        before = git(self.worker, 'rev-parse', 'HEAD').stdout
        self.assertEqual(self.publish().returncode, 0)
        self.assertEqual(git(self.worker, 'rev-parse', 'HEAD').stdout, before)

    def test_publish_rejection_stays_failed_so_line_cannot_run(self):
        (self.worker / 'remote/system.json').write_text(json.dumps({'revision': 'new feed'}))
        git(self.worker, 'add', 'remote/system.json')
        git(self.worker, 'commit', '-m', 'new feed awaiting report')
        git(self.worker, 'push')
        hook = self.remote / 'hooks/pre-receive'
        hook.write_text('#!/bin/sh\nexit 1\n')
        hook.chmod(0o755)
        (self.worker / 'remote/brief.json').write_text(json.dumps({'close': 'changed'}))
        before = git(self.base, '--git-dir='+str(self.remote), 'rev-parse', 'main').stdout
        result = self.publish()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Could not publish', result.stdout)
        self.assertEqual(git(self.base, '--git-dir='+str(self.remote), 'rev-parse', 'main').stdout, before)

    def test_send_race_keeps_first_published_outbox_and_other_edition(self):
        import shutil
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from scripts.line_outbox import freeze, load
        now = datetime.now(ZoneInfo('Asia/Taipei'))
        day = now.date().isoformat()
        source = WORKFLOW.parents[2]
        for name in ['send_line_brief.py', 'line_outbox.py']:
            shutil.copy(source / 'scripts' / name, self.worker / 'scripts' / name)
        # Make these helpers available in both checkouts before the race.
        (self.worker / 'scripts/build_daily_brief.py').write_text(textwrap.dedent("""
            import json
            from pathlib import Path
            p = Path('remote/brief.json')
            doc = json.loads(p.read_text())
            doc['close']['title'] = 'new report after race'
            p.write_text(json.dumps(doc))
        """))
        git(self.worker, 'add', '.')
        git(self.worker, 'commit', '-m', 'outbox helpers')
        git(self.worker, 'push')
        git(self.peer, 'pull', '--ff-only')
        report = {'date': day, 'edition': 'close', 'status': 'ready', 'title': 'FIRST PUBLISHED'}
        doc = {'morning': 'preserve peer edition', 'close': report}
        (self.peer / 'remote/brief.json').write_text(json.dumps(doc))
        freeze(doc, 'close', now, self.peer / 'remote/line_outbox.json', {})
        original = (self.peer / 'remote/line_outbox.json').read_bytes()
        git(self.peer, 'add', '.')
        git(self.peer, 'commit', '-m', 'first published immutable message')
        git(self.peer, 'push')
        (self.worker / 'remote/brief.json').write_text(json.dumps({'close': {**report, 'title': 'losing concurrent report'}}))
        result = self.publish(send=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        actual = git(self.base, '--git-dir='+str(self.remote), 'show', 'main:remote/line_outbox.json').stdout.encode()
        self.assertEqual(actual, original)
        published = json.loads(git(self.base, '--git-dir='+str(self.remote), 'show', 'main:remote/brief.json').stdout)
        self.assertEqual(published['morning'], 'preserve peer edition')
        self.assertIn('FIRST PUBLISHED', load(self.worker / 'remote/line_outbox.json', day, 'close')['messages'][0]['text'])
