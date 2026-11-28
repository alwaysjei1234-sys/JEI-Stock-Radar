"""Explicit source-date conflicts must never become frozen forward signals."""
import copy
import unittest
from datetime import datetime
from test_pick_validation import archive, feed, TZ, DATES
from scripts.update_pick_validation import close_verified, update


class PickSourceDateGuardTests(unittest.TestCase):
    def check_conflict(self, source_field):
        f = feed()
        if source_field == 'source_data_date':
            f[source_field] = '2026-10-12'
        else:
            f['market'][source_field] = '2026-10-12'
        prior = {'schema': 1, 'picks': []}
        original = copy.deepcopy(prior)
        a = archive(1)
        self.assertFalse(close_verified(f, a, DATES[0]))
        state, report, captured = update(f, a, prior, datetime(2026, 10, 13, 16, tzinfo=TZ))
        self.assertFalse(captured)
        self.assertEqual(state['picks'], [])
        self.assertEqual(prior, original)
        self.assertEqual(report['total_frozen_picks'], 0)

    def test_feed_source_date_conflict_never_freezes(self):
        self.check_conflict('source_data_date')

    def test_market_source_date_conflict_never_freezes(self):
        self.check_conflict('market_data_as_of')

    def test_matching_explicit_source_dates_still_freeze(self):
        f = feed()
        f['source_data_date'] = DATES[0]
        f['market']['market_data_as_of'] = DATES[0]
        prior = {'schema': 1, 'picks': []}
        self.assertTrue(close_verified(f, archive(1), DATES[0]))
        state, report, captured = update(f, archive(1), prior,
            datetime(2026, 10, 13, 16, tzinfo=TZ))
        self.assertTrue(captured)
        self.assertEqual(len(state['picks']), 10)
        self.assertEqual(prior['picks'], [])
