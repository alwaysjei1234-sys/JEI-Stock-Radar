import copy
import unittest
from datetime import datetime

from scripts.recover_pick_history import recover
from scripts.update_pick_validation import TZ, freeze_picks
from test_pick_validation import archive, feed, DATES


class RecoveryTests(unittest.TestCase):
    def fixture(self):
        a = archive(3)
        prior = {"schema": 1, "picks": freeze_picks(feed(), a["days"][DATES[0]], DATES[0])}
        snapshots = []
        for i, day in enumerate(DATES[1:3], 1):
            f = feed(day)
            for group in ("attack", "next", "monster", "tomorrow_monster", "future_monster"):
                f[group][0]["price"] = a["days"][day]["2344"]
                f[group][1]["price"] = a["days"][day]["2603"]
            snapshots.append({"sha": str(i)*40, "blob": "a"*40,
                              "committed_at": day+"T16:00:00+08:00", "feed": f})
        return prior, a, snapshots, datetime(2026, 10, 15, 17, tzinfo=TZ)

    def test_recovers_all_days_preserves_old_records_and_first_publication(self):
        prior, a, sources, now = self.fixture()
        original = copy.deepcopy(prior)
        revised = copy.deepcopy(sources[0])
        revised["feed"]["attack"][0]["score"] = 99
        revised["sha"] = "f"*40
        state, proof = recover(prior, a, [sources[0], revised, sources[1]], now)
        self.assertEqual(prior, original)
        self.assertEqual(state["picks"][:10], prior["picks"])
        self.assertEqual(len(state["picks"]), 30)
        self.assertEqual(state["picks"][10]["source_commit"], "1"*40)
        self.assertEqual(state["picks"][10]["score"], 95)
        self.assertEqual(len(proof), 2)
        again, proof = recover(state, a, sources, now)
        self.assertEqual(again, state)
        self.assertEqual(proof, [])

    def test_missing_day_fails_without_partial_mutation(self):
        prior, a, sources, now = self.fixture()
        original = copy.deepcopy(prior)
        with self.assertRaisesRegex(ValueError, "No contemporaneous"):
            recover(prior, a, sources[1:], now)
        self.assertEqual(prior, original)

    def test_late_or_future_publication_is_not_contemporaneous(self):
        for stamp in ("2026-10-15T16:00:00+08:00", "2026-10-14T15:00:00+08:00"):
            prior, a, sources, now = self.fixture()
            sources[0]["committed_at"] = stamp
            with self.assertRaisesRegex(ValueError, "No contemporaneous"):
                recover(prior, a, sources, now)

    def test_private_or_unverified_feed_is_not_imported(self):
        prior, a, sources, now = self.fixture()
        sources[0]["feed"]["holdings"] = {"2330": {"cost": 123}}
        with self.assertRaisesRegex(ValueError, "No contemporaneous"):
            recover(prior, a, sources, now)
