import unittest
from tools.jei_actions_audit import AREAS, build_report, inspect_feed, heartbeat_status
import datetime as dt
import json
import tempfile
from pathlib import Path

class AuditTests(unittest.TestCase):
    def test_missing_keys_and_bad_date(self):
        result = inspect_feed({'data_date': 'not-a-date'})
        self.assertIn('invalid_data_date', result['issues'])
        self.assertIn('missing:market', result['issues'])

    def test_red_risk_not_claim_delivery(self):
        feed = {'data_date':'2026-11-06', 'risk':{'level':'red','score':100}, 'market':{}}
        report = build_report(feed, 'abc')
        self.assertEqual(report['results']['line_delivery'], 'NOT_TESTED')
        self.assertIsNone(report['completion_percent'])
        self.assertEqual(report['source_commit'], 'abc')

    def test_critical_missing_fields_fail(self):
        result = inspect_feed({'data_date': '2026-11-06', 'risk': {}, 'market': {}})
        self.assertEqual(result['status'], 'failed')
        self.assertIn('missing:summary', result['critical_issues'])

    def test_valid_feed_does_not_claim_live_delivery(self):
        from tools.jei_actions_audit import REQUIRED
        feed = {key: {} for key in REQUIRED}
        feed.update({'data_date': '2026-11-06', 'risk': {'level': 'red', 'score': 100}, 'market': {}})
        result = inspect_feed(feed)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['line_delivery'], 'NOT_TESTED')

    def test_explicit_stale_official_close_fails_audit(self):
        from tools.jei_actions_audit import REQUIRED
        feed = {key: {} for key in REQUIRED}
        feed.update({'data_date': '2026-11-13', 'risk': {},
                     'market': {'post_close_refresh': True, 'stale': True,
                                'session_status': '已驗證'}})
        result = inspect_feed(feed)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('stale_official_close', result['critical_issues'])

    def test_unverified_official_close_fails_audit(self):
        from tools.jei_actions_audit import REQUIRED
        feed = {key: {} for key in REQUIRED}
        feed.update({'data_date': '2026-11-13', 'risk': {},
                     'market': {'post_close_refresh': True, 'stale': False,
                                'session_status': '待驗證'}})
        self.assertIn('unverified_official_close', inspect_feed(feed)['critical_issues'])

    def test_off_session_no_live_quotes_is_not_critical(self):
        from tools.jei_actions_audit import REQUIRED
        feed = {key: {} for key in REQUIRED}
        feed.update({'data_date': '2026-11-13', 'risk': {},
                     'market': {'post_close_refresh': True, 'stale': False,
                                'session_status': '已驗證', 'live_valid': False,
                                'live_count': 0}})
        self.assertEqual(inspect_feed(feed)['status'], 'ok')

    def test_unverified_institutional_is_reported_not_falsely_verified(self):
        from tools.jei_actions_audit import REQUIRED
        feed = {key: {} for key in REQUIRED}
        feed.update({'data_date': '2026-11-13', 'risk': {}, 'market': {},
                     'institutional_status': {'ok': False, 'count': 0}})
        result = inspect_feed(feed)
        self.assertIs(result['institutional_verified'], False)
        self.assertTrue(any('institutional_unverified' in issue for issue in result['issues']))
        self.assertEqual(result['status'], 'ok')  # degraded source, not a false full outage

    def test_missing_colab_heartbeat_is_unknown_not_stopped(self):
        self.assertEqual(heartbeat_status()['status'], 'UNKNOWN')
        self.assertEqual(heartbeat_status('/no/such/drive/heartbeat.json')['status'], 'UNKNOWN')
        self.assertEqual(build_report({}, 'abc')['colab_heartbeat']['status'], 'UNKNOWN')

    def test_heartbeat_fresh_stale_and_timezone_missing(self):
        now = dt.datetime(2026, 11, 13, 16, 0, tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'heartbeat.json'
            path.write_text(json.dumps({'checked_at': '2026-11-13T15:55:00Z'}))
            self.assertEqual(heartbeat_status(path, now)['status'], 'FRESH')
            path.write_text(json.dumps({'checked_at': '2026-11-13T15:00:00Z'}))
            self.assertEqual(heartbeat_status(path, now)['status'], 'STALE')
            path.write_text(json.dumps({'checked_at': '2026-11-13T15:55:00'}))
            self.assertEqual(heartbeat_status(path, now)['status'], 'UNKNOWN')

    def test_working_31_labels(self):
        self.assertEqual(len(AREAS), 31)

if __name__ == '__main__':
    unittest.main()
