"""Known exchange closures must never become newly frozen pick cohorts."""
import copy
import unittest
from datetime import datetime

from test_pick_validation import TZ, DATES, archive, feed
from scripts.update_pick_validation import close_verified, update


def dated_archive(day):
    result = archive(1)
    result['days'] = {day: result['days'][DATES[0]]}
    return result


class ClosedSessionCaptureTests(unittest.TestCase):
    def test_known_closed_signal_dates_are_rejected(self):
        for day in ('2026-11-28', '2026-11-29', '2026-10-09', '2026-10-23'):
            with self.subTest(day=day):
                self.assertFalse(close_verified(feed(day), dated_archive(day), day))

    def test_first_import_cannot_freeze_closed_day_picks_or_empty_session(self):
        for day in ('2026-11-28', '2026-10-09'):
            for empty in (False, True):
                with self.subTest(day=day, empty=empty):
                    source = feed(day)
                    if empty:
                        for group in ('attack', 'next', 'monster', 'tomorrow_monster', 'future_monster'):
                            source[group] = []
                    prior = {'schema': 1, 'picks': []}
                    original = copy.deepcopy(prior)
                    ledger, report, captured = update(
                        source, dated_archive(day), prior,
                        datetime.fromisoformat(day + 'T16:00:00').replace(tzinfo=TZ))
                    self.assertFalse(captured)
                    self.assertEqual(ledger['picks'], [])
                    self.assertNotIn('empty_sessions', ledger)
                    self.assertEqual(prior, original)
                    self.assertEqual(report['total_frozen_picks'], 0)

    def test_weekend_import_of_verified_friday_close_remains_supported(self):
        day = '2026-11-27'
        prior = {'schema': 1, 'picks': []}
        ledger, report, captured = update(
            feed(day), dated_archive(day), prior,
            datetime(2026, 11, 28, 16, tzinfo=TZ))
        self.assertTrue(captured)
        self.assertEqual(len(ledger['picks']), 10)
        self.assertTrue(all(p['day'] == day and p['origin'] == 'verified_archive_bootstrap'
                            for p in ledger['picks']))
        self.assertEqual(prior['picks'], [])
        self.assertEqual(report['total_frozen_picks'], 10)
