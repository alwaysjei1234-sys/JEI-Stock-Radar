"""Paper observations cannot start on a known exchange closure."""
import copy
import unittest
from scripts.update_paper_performance import advance, initial_state, validate
from test_paper_performance import archive, feed


class PaperClosedSessionTests(unittest.TestCase):
    def test_paper_close_validator_rejects_known_closed_dates(self):
        for day in ('2026-11-28', '2026-11-29', '2026-10-09', '2026-10-23'):
            with self.subTest(day=day), self.assertRaises(ValueError):
                validate(feed(day), archive((day, 100)), day)

    def test_initial_closed_day_never_mutates_signals_or_equity(self):
        for day in ('2026-11-28', '2026-10-09', '2026-10-23'):
            state = initial_state()
            original = copy.deepcopy(state)
            with self.subTest(day=day):
                with self.assertRaises(ValueError):
                    advance(feed(day), archive((day, 100)), state, day)
                self.assertEqual(state, original)

    def test_friday_signal_enters_on_monday_without_weekend_observation(self):
        friday, monday = '2026-11-27', '2026-11-30'
        state = initial_state()
        prices = archive((friday, 100), (monday, 101))
        self.assertTrue(advance(feed(friday), prices, state, friday))
        self.assertEqual(len(state['signals']), 1)
        self.assertEqual(state['strategies']['fixed5']['positions'], [])
        self.assertTrue(advance(feed(monday, False), prices, state, monday))
        self.assertEqual(state['last_processed_day'], monday)
        for account in state['strategies'].values():
            self.assertEqual(account['positions'][0]['entry_day'], monday)
            self.assertEqual(len(account['equity_history']), 2)
