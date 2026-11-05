"""Do not fan out to MIS once no execution can pass the freshness gate."""
import unittest
from datetime import datetime
from scripts import update_system as u


class MisClosedWindowTests(unittest.TestCase):
    def exercise(self, hour, minute, expected):
        import test_midnight_archive_recovery as fixture
        calls = []

        def live(rows, **kwargs):
            calls.append(len(rows))
            return rows, 0, None, [], {}

        snapshots = fixture.MidnightArchiveRecoveryTests().exercise(
            [datetime(2026, 11, 4, hour, minute, tzinfo=u.TZ)], live_impl=live)
        self.assertEqual(bool(calls), expected)
        self.assertEqual(snapshots[0]['market']['live_diagnostics']['attempted'], expected)

    def test_regular_session_still_refreshes(self):
        self.exercise(9, 5, True)

    def test_last_possible_fresh_close_minute_is_retained(self):
        self.exercise(13, 40, True)

    def test_expired_close_window_skips_full_scan(self):
        self.exercise(13, 41, False)

    def test_official_close_wait_does_not_scan_expired_trades(self):
        self.exercise(14, 0, False)
        self.exercise(15, 59, False)
