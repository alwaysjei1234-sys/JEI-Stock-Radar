#!/usr/bin/env python3
"""Pure deterministic fixtures: no broker and no network calls."""
import copy
import unittest
from scripts.update_paper_performance import advance, initial_state

DAY1 = "2026-10-13"
DAY2 = "2026-10-14"
DAY3 = "2026-10-15"
DAY4 = "2026-10-16"

def prices(value):
    data = {str(1000 + i): 100.0 for i in range(600)}
    data["2603"] = float(value)
    return data

def feed(day, attack=True, stale=False, mode="今日收盤"):
    return {
        "data_date": day,
        "updated_at": day + " 14:45",
        "market": {"mode": mode, "stale": stale, "close_count": 600},
        "attack": [{"code": "2603", "name": "長榮", "score": 92}] if attack else [],
        "monster": [],
        "holdings": {"PRIVATE": {"cost": 123456}},
    }

def archive(*days):
    return {"schema": 1, "kind": "official_daily_close",
            "days": {d: prices(p) for d, p in days}}

class TestDailyStrategyEngine(unittest.TestCase):
    def test_no_same_day_entry_and_next_day_exit(self):
        state = initial_state()
        a = archive((DAY1, 100.0))
        self.assertTrue(advance(feed(DAY1), a, state, DAY1))
        self.assertEqual(state["latest_signal_count"], 1)
        self.assertEqual(state["strategies"]["fixed5"]["positions"], [])

        a["days"][DAY2] = prices(100.0)
        self.assertTrue(advance(feed(DAY2, False), a, state, DAY2))
        for account in state["strategies"].values():
            self.assertEqual(len(account["positions"]), 1)
            self.assertEqual(len(account["closed"]), 0)
            self.assertEqual(account["positions"][0]["entry_day"], DAY2)
            self.assertLessEqual(account["positions"][0]["entry_cost"], 100000)
            self.assertGreaterEqual(account["cash"], 0)

        a["days"][DAY3] = prices(106.0)
        self.assertTrue(advance(feed(DAY3, False), a, state, DAY3))
        fixed5 = state["strategies"]["fixed5"]
        self.assertEqual(len(fixed5["closed"]), 1)
        self.assertEqual(fixed5["closed"][0]["exit_day"], DAY3)
        self.assertLess(fixed5["closed"][0]["net_return_pct"], 6)
        self.assertGreater(fixed5["closed"][0]["net_return_pct"], 5)
        self.assertEqual(len(state["strategies"]["fixed7"]["closed"]), 0)
        self.assertEqual(len(state["strategies"]["trailing"]["closed"]), 0)

        before = copy.deepcopy(state)
        self.assertFalse(advance(feed(DAY3, False), a, state, DAY3))
        self.assertEqual(before, state, "same day processing must be idempotent")

        a["days"][DAY4] = prices(103.0)
        self.assertTrue(advance(feed(DAY4, False), a, state, DAY4))
        self.assertEqual(state["strategies"]["trailing"]["closed"][0]["reason"], "移動停利觸發")
        self.assertEqual(len(state["strategies"]["fixed7"]["closed"]), 0)
        self.assertEqual(len(state["strategies"]["fixed10"]["closed"]), 0)
        self.assertEqual(state["strategies"]["fixed5"]["summary"]["open_positions"], 0)
        self.assertNotIn("holdings", str(state))
        self.assertNotIn("123456", str(state))

    def test_stale_invalid_or_missing_daily_data_never_processes(self):
        original = initial_state()
        a = archive((DAY1, 100.0))
        for invalid in [feed(DAY1, stale=True), feed(DAY1, mode="盤中即時"), feed(DAY2)]:
            state = copy.deepcopy(original)
            with self.assertRaises(ValueError):
                advance(invalid, a, state, DAY1)
            self.assertEqual(state, original)
        a["days"][DAY1] = {"2603": 100.0}
        with self.assertRaises(ValueError):
            advance(feed(DAY1), a, copy.deepcopy(original), DAY1)

    def test_official_close_must_be_published_after_1330(self):
        a = archive((DAY1, 100.0))
        original = initial_state()
        cases = [
            {**feed(DAY1), "updated_at": DAY1 + " 12:35"},
            {**feed(DAY1), "updated_at": DAY2 + " 14:45"},
            {**feed(DAY1), "updated_at": "invalid date"},
            {**feed(DAY1), "updated_at": DAY1 + " 13:29"},
            {**feed(DAY1), "market": {**feed(DAY1)["market"], "close_count": True}},
            {**feed(DAY1), "market": {**feed(DAY1)["market"], "close_count": "1954"}},
        ]
        for item in cases:
            with self.subTest(snapshot=item):
                state = copy.deepcopy(original)
                with self.assertRaises(ValueError):
                    advance(item, a, state, DAY1)
                self.assertEqual(state, original, "invalid timestamps must not mutate any P&L")
        ready = feed(DAY1)
        ready["updated_at"] = DAY1 + " 13:30"
        state = initial_state()
        self.assertTrue(advance(ready, a, state, DAY1))

    def test_500_valid_quotes_not_merely_500_json_keys(self):
        a = archive((DAY1, 100.0))
        a["days"][DAY1] = {str(1000+i): "not-a-price" for i in range(600)}
        a["days"][DAY1]["2603"] = 100
        state = initial_state()
        with self.assertRaisesRegex(ValueError, "有效官方收盤價不足"):
            advance(feed(DAY1), a, state, DAY1)
        self.assertIsNone(state["last_processed_day"])

    def test_gap_in_archived_trading_days_does_not_fabricate_fills(self):
        state = initial_state()
        a = archive((DAY1, 100.0))
        advance(feed(DAY1), a, state, DAY1)
        # A valid archived 10/14 close exists, but the daily job never processed it.
        a["days"][DAY2] = prices(100.0)
        a["days"][DAY3] = prices(106.0)
        previous = copy.deepcopy(state)
        with self.assertRaisesRegex(ValueError, "交易日出現缺口"):
            advance(feed(DAY3), a, state, DAY3)
        self.assertEqual(state, previous, "an unprocessed day must not alter P&L")
        advance(feed(DAY2, False), a, state, DAY2)
        self.assertTrue(advance(feed(DAY3, False), a, state, DAY3))

    def test_stop_loss_and_hypothetical_cash_limits(self):
        s = initial_state()
        a = archive((DAY1, 100.0), (DAY2, 100.0), (DAY3, 96.0))
        advance(feed(DAY1), a, s, DAY1)
        advance(feed(DAY2, False), a, s, DAY2)
        advance(feed(DAY3, False), a, s, DAY3)
        for v in s["strategies"].values():
            self.assertEqual(v["closed"][0]["reason"], "收盤停損")
            self.assertLess(v["closed"][0]["net"], 0)
            self.assertGreaterEqual(v["cash"], 0)

if __name__ == "__main__":
    unittest.main()
