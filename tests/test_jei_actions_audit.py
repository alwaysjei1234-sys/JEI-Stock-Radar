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

    def test_public_holdings_must_be_present_and_safe(self):
        from tools.jei_actions_audit import REQUIRED

        feed = {key: {} for key in REQUIRED}
        feed.update(data_date="2026-11-13", holdings={"2330": {"score": 70}})
        self.assertEqual(inspect_feed(feed)["status"], "ok")
        for invalid in (None, [], {"2330": {"cost": 1}}):
            with self.subTest(invalid=invalid):
                self.assertIn("invalid_public_holdings", inspect_feed(
                    {**feed, "holdings": invalid})["critical_issues"])
        del feed["holdings"]
        self.assertIn("missing:holdings", inspect_feed(feed)["critical_issues"])

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

    def test_verified_official_close_rejects_mixed_dates(self):
        from tools.jei_actions_audit import REQUIRED

        feed = {key: {} for key in REQUIRED}
        feed.update(data_date="2026-11-13", source_data_date="2026-11-13",
                    market={"post_close_refresh": True, "session_status": "已驗證",
                            "market_data_as_of": "2026-11-13"})
        self.assertEqual(inspect_feed(feed)["status"], "ok")
        for candidate in (
            {**feed, "source_data_date": "TWSE:2026-11-13 / TPEx:2026-11-12"},
            {**feed, "market": {**feed["market"], "market_data_as_of": "2026-11-12"}},
        ):
            self.assertIn("official_close_date_mismatch", inspect_feed(candidate)["critical_issues"])

    def test_archive_can_report_lagging_source_date(self):
        from tools.jei_actions_audit import REQUIRED

        feed = {key: {} for key in REQUIRED}
        feed.update(data_date="2026-11-13", source_data_date="2026-11-12",
                    market={"post_close_refresh": False, "historical_readonly": True,
                            "market_data_as_of": "2026-11-13"})
        self.assertEqual(inspect_feed(feed)["status"], "ok")

    def test_off_session_no_live_quotes_is_not_critical(self):
        from tools.jei_actions_audit import REQUIRED
        feed = {key: {} for key in REQUIRED}
        feed.update({'data_date': '2026-11-13', 'risk': {},
                     'market': {'post_close_refresh': True, 'stale': False,
                                'session_status': '已驗證', 'live_valid': False,
                                'live_count': 0}})
        self.assertEqual(inspect_feed(feed)['status'], 'ok')

    def test_intraday_unverified_quotes_fail_audit(self):
        from tools.jei_actions_audit import REQUIRED

        now = dt.datetime(2026, 11, 13, 10, 20, tzinfo=dt.timezone(dt.timedelta(hours=8)))
        feed = dict.fromkeys(REQUIRED, {})
        feed["data_date"] = "2026-11-13"
        for count in (0, 120):
            with self.subTest(count=count):
                feed["market"] = {
                    "last_checked_at": "2026-11-13 10:20",
                    "live_count": count, "live_valid": False,
                    "live_diagnostics": {"market_open": True, "quote_refresh_window": True},
                }
                self.assertIn("unverified_intraday_quotes", inspect_feed(feed, now=now)["critical_issues"])
                feed["market"]["live_diagnostics"]["quote_refresh_window"] = False
                self.assertEqual(inspect_feed(feed, now=now)["status"], "ok")
        feed["market"].update(live_count=600, live_valid=True)
        feed["market"]["live_diagnostics"]["quote_refresh_window"] = True
        self.assertEqual(inspect_feed(feed, now=now)["status"], "ok")

    def test_intraday_check_time_cannot_be_bypassed_by_stale_feed_flags(self):
        from tools.jei_actions_audit import REQUIRED
        zone = dt.timezone(dt.timedelta(hours=8))
        now = dt.datetime(2026, 11, 20, 10, 20, tzinfo=zone)
        for active in (True, False):
            feed = {key: {} for key in REQUIRED}
            feed.update(data_date="2026-11-20", market={
                "live_valid": True, "live_count": 700,
                "last_checked_at": "2026-11-20 10:09",
                "live_diagnostics": {"market_open": active, "quote_refresh_window": active},
            })
            with self.subTest(active=active):
                result = inspect_feed(feed, now=now)
                self.assertEqual(result["status"], "failed")
                self.assertIn("stale_intraday_check_timestamp", result["critical_issues"])

    def test_intraday_timestamp_boundaries_and_closed_sessions(self):
        from tools.jei_actions_audit import REQUIRED
        zone = dt.timezone(dt.timedelta(hours=8))
        now = dt.datetime(2026, 11, 20, 10, 20, tzinfo=zone)
        feed = {key: {} for key in REQUIRED}
        feed.update(data_date="2026-11-20", market={
            "live_valid": True, "live_count": 700,
            "live_diagnostics": {"market_open": True, "quote_refresh_window": True}})
        for stamp, expired in (("2026-11-20 10:10", False),
                               ("2026-11-20 10:09", True),
                               ("2026-11-20 10:22", False),
                               ("2026-11-20 10:23", True),
                               ("2026-11-19 10:20", True), ("invalid", True), (None, True)):
            feed["market"]["last_checked_at"] = stamp
            with self.subTest(stamp=stamp):
                for clock in (now, now.astimezone(dt.timezone.utc)):
                    result = inspect_feed(feed, now=clock)
                    self.assertEqual("stale_intraday_check_timestamp" in result["critical_issues"], expired)
        for clock in (now.replace(hour=8), now.replace(hour=14), now.replace(day=21),
                      now.replace(month=12, day=25), now.replace(month=10, day=23)):
            with self.subTest(clock=clock):
                self.assertNotIn("stale_intraday_check_timestamp",inspect_feed(feed,now=clock)["critical_issues"])
        with self.assertRaises(ValueError):
            inspect_feed(feed, now=now.replace(tzinfo=None))

    def test_cli_stale_snapshot_fails_and_preserves_diagnostic_artifact(self):
        import sys
        from unittest.mock import patch
        from tools import jei_actions_audit as audit
        original = dt.datetime
        class Clock(original):
            @classmethod
            def now(cls, tz=None):
                value = original(2026, 11, 20, 2, 20, tzinfo=dt.timezone.utc)
                return value.astimezone(tz) if tz else value.replace(tzinfo=None)
        feed = json.loads(Path('remote/system.json').read_text())
        # Replay yesterday's valid off-session shape at today's real trading clock.
        feed['market']['last_checked_at'] = '2026-11-19 19:05'
        feed['market']['live_diagnostics'] = {'market_open': False, 'quote_refresh_window': False}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp);source = root/'system.json';source.write_text(json.dumps(feed))
            with patch.object(audit.dt, 'datetime', Clock), patch.object(sys,'argv',
                    ['audit','--feed',str(source),'--out',str(root/'out'),'--commit','a'*40]):
                self.assertEqual(audit.main(),1)
            report = json.loads((root/'out/jei_audit.json').read_text())
            self.assertIn('stale_intraday_check_timestamp',report['results']['critical_issues'])
            self.assertEqual(report['results']['line_delivery'],'NOT_TESTED')
            self.assertIsNone(report['completion_percent'])

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
            path.write_text(json.dumps({'schema': 1, 'provider': 'google_colab', 'session_id': 'test', 'source_commit': 'a' * 40, 'heartbeat_at_utc': '2026-11-13T15:55:00Z'}))
            self.assertEqual(heartbeat_status(path, now)['status'], 'RECENT_HEARTBEAT')
            path.write_text(json.dumps({'schema': 1, 'provider': 'google_colab', 'session_id': 'test', 'source_commit': 'a' * 40, 'heartbeat_at_utc': '2026-11-13T15:00:00Z'}))
            self.assertEqual(heartbeat_status(path, now)['status'], 'STALE')
            path.write_text(json.dumps({'schema': 1, 'provider': 'google_colab', 'session_id': 'test', 'source_commit': 'a' * 40, 'heartbeat_at_utc': '2026-11-13T15:55:00'}))
            self.assertEqual(heartbeat_status(path, now)['status'], 'UNKNOWN')

    def test_heartbeat_file_matches_emitter_contract(self):
        from tools.jei_colab_heartbeat import heartbeat_payload, write_heartbeat

        now = dt.datetime(2026, 11, 14, 1, tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "heartbeat.json"
            payload = heartbeat_payload("test", "a" * 40, now=now)
            write_heartbeat(path, payload)
            self.assertEqual(heartbeat_status(path, now)["status"], "RECENT_HEARTBEAT")
            write_heartbeat(path, {**payload, "provider": "github_actions"})
            self.assertEqual(heartbeat_status(path, now)["status"], "UNKNOWN")

    def test_working_31_labels(self):
        self.assertEqual(len(AREAS), 31)

if __name__ == '__main__':
    unittest.main()
