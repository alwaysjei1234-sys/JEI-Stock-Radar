"""A failed recheck must not claim today's already-verified close never existed."""
import unittest
from datetime import datetime
from scripts import update_system as u
import test_midnight_archive_recovery as fixtures


class SameDayRetryStatusTests(unittest.TestCase):
    def exercise(self, moments):
        fixture = fixtures.MidnightArchiveRecoveryTests()
        original = fixture.prior()
        original['data_date'] = '2026-11-04'
        original['updated_at'] = '2026-11-04 17:03'
        original['risk']['as_of'] = '2026-11-04'
        fixture.prior = lambda: original
        return fixture.exercise(moments)

    def test_repeated_same_day_failure_is_explicit_without_refreshing_close_time(self):
        moments = [datetime(2026, 11, 4, h, 1, tzinfo=u.TZ) for h in (18, 19)]
        for snapshot in self.exercise(moments):
            market = snapshot['market']
            self.assertEqual(market['session_status'], '收盤重驗失敗')
            self.assertIn('保留今日已驗證收盤', snapshot['summary'])
            self.assertNotIn('當日官方收盤尚未完成', snapshot['summary'])
            self.assertEqual(market['live_diagnostics']['reason'], market['session_reason'])
            self.assertIn(market['session_reason'], snapshot['summary'])
            self.assertEqual(snapshot['updated_at'], '2026-11-04 17:03')
            self.assertTrue(market['historical_readonly'])
            self.assertTrue(market['no_new_picks'])
            self.assertFalse(snapshot['risk']['actionable'])

    def test_next_session_still_waits_for_new_official_close(self):
        snapshot = self.exercise([datetime(2026, 11, 5, 18, 1, tzinfo=u.TZ)])[0]
        self.assertEqual(snapshot['market']['session_status'], '交易日資料待驗證')
        self.assertIn('當日官方收盤尚未完成', snapshot['summary'])

    def test_next_day_preopen_keeps_preopen_status(self):
        snapshot = self.exercise([datetime(2026, 11, 5, 8, 45, tzinfo=u.TZ)])[0]
        self.assertEqual(snapshot['market']['session_status'], '盤前準備')
        self.assertNotIn('重驗失敗', snapshot['summary'])
