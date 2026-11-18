"""Regression for the observed-loss strategy guard; never claim OOS or trading profit."""
import copy
import json
import unittest
from pathlib import Path

from scripts.strategy_health import assess_observed_quality, annotate_public_feed

GROUPS = ("attack", "next", "monster", "tomorrow_monster", "future_monster")


def example_report(*, day="2026-11-17", winning=None):
    report = {"schema": 1, "mode": "forward_official_close_pick_validation",
              "latest_official_day": day, "groups": {}}
    for name in GROUPS:
        report["groups"][name] = {}
        for horizon in ("3", "7"):
            good = (name, horizon) == winning
            report["groups"][name][horizon] = {
                "completed": 40, "win_rate_pct": 65.0 if good else 22.5,
                "avg_estimated_net_pct": 3.0 if good else -4.0,
            }
    return report


def example_feed():
    return {
        "risk": {"actionable": True, "score": 64,
                 "reasons": ["official TWSE index verified"]},
        "market": {"live_valid": True, "no_new_picks": False,
                   "mode": "盤中即時"},
        "priority": [{"title": "main", "note": "score=88", "action": "主攻#1"},
                     {"title": "next", "note": "score=81", "action": "下一棒#1"}],
        "attack": [{"code": "1234", "score": 88, "reason": "成交量價已驗證"}],
        "next": [{"code": "2345", "score": 81, "reason": "正常準備發動"}],
        "monster": [{"code": "3456", "score": 92, "reason": "價量突破"}],
        "tomorrow_monster": [], "future_monster": [], "rotate": [],
        "backtest": {"history": [1, 2, 3]},
    }


class StrategyHealthTests(unittest.TestCase):
    def test_all_ten_windows_underperform_annotates_visible_signals(self):
        feed = example_feed()
        before = copy.deepcopy(feed)
        health = annotate_public_feed(feed, example_report(), "2026-11-18",
                                      market_open=True)
        self.assertEqual(health["evaluated_windows"], 10)
        self.assertEqual(health["underperforming_windows"], 10)
        self.assertEqual(health["recommendation_mode"], "research_only")
        self.assertFalse(health["independent_oos_verified"])
        self.assertFalse(health["automatic_trade_block"])
        self.assertEqual(feed["priority"][0]["action"], "僅模擬研究")
        self.assertEqual(feed["attack"][0]["score"], before["attack"][0]["score"])
        self.assertEqual(feed["attack"][0]["code"], before["attack"][0]["code"])
        self.assertEqual(feed["attack"][0]["trade_readiness"], "research_only")
        self.assertIn("僅供模擬研究", feed["attack"][0]["reason"])
        self.assertIn("僅供模擬研究", feed["monster"][0]["reason"])
        self.assertTrue(feed["risk"]["strategy_quality_alert"])
        self.assertTrue(feed["risk"]["actionable"])  # quote validity untouched
        self.assertFalse(feed["market"]["no_new_picks"])  # no retroactive erasure
        self.assertEqual(feed["market"]["candidate_readiness"], "research_only")
        self.assertEqual(feed["backtest"], before["backtest"])

    def test_one_healthy_window_not_claimed_all_bad(self):
        feed = example_feed()
        health = annotate_public_feed(feed, example_report(winning=("attack", "3")),
                                      "2026-11-18", market_open=True)
        self.assertEqual(health["status"], "SOME_OBSERVED_SHORT_HORIZONS_WEAK")
        self.assertEqual(health["evaluated_windows"], 10)
        self.assertEqual(health["underperforming_windows"], 9)
        self.assertNotIn("trade_readiness", feed["attack"][0])
        self.assertEqual(feed["priority"][0]["action"], "主攻#1")

    def test_missing_or_immature_windows_never_look_like_profit(self):
        report = example_report()
        report["groups"]["next"]["7"]["completed"] = 29
        health = assess_observed_quality(report, "2026-11-18", market_open=True)
        self.assertEqual(health["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(health["recommendation_mode"], "unverified")
        self.assertFalse(health["independent_oos_verified"])

    def test_intraday_future_looking_and_stale_evidence_fail_closed(self):
        for day, today, market_open in [
            ("2026-11-18", "2026-11-18", True),
            ("2026-11-19", "2026-11-18", True),
            ("2026-11-05", "2026-11-18", True),
            ("2026-02-30", "2026-11-18", True),
        ]:
            with self.subTest(day=day):
                q = assess_observed_quality(example_report(day=day), today,
                                            market_open=market_open)
                self.assertEqual(q["status"], "UNVERIFIED")
                self.assertEqual(q["recommendation_mode"], "unverified")
        after_close = assess_observed_quality(example_report(day="2026-11-18"),
                                              "2026-11-18", market_open=False)
        self.assertEqual(after_close["status"], "ALL_OBSERVED_SHORT_HORIZONS_WEAK")

    def test_corrupted_or_noncanonical_report_never_blocks_picks(self):
        for report in (None, [], {}, {"schema": 1, "mode": "not_real"},
                       {"schema": 1, "mode": "forward_official_close_pick_validation",
                        "latest_official_day": "2026-11-17", "groups": None}):
            with self.subTest(report=report):
                feed = example_feed()
                before = copy.deepcopy(feed)
                health = annotate_public_feed(feed, report, "2026-11-18")
                self.assertNotEqual(health["recommendation_mode"], "research_only")
                self.assertEqual(feed["attack"], before["attack"])
                self.assertEqual(feed["risk"], before["risk"])
                self.assertFalse(health["live_trading_verified"])

    def test_nan_boolean_or_invalid_return_cannot_trigger_false_quality_label(self):
        for changed in (
            {"completed": True}, {"win_rate_pct": True},
            {"avg_estimated_net_pct": float("nan")},
            {"win_rate_pct": 150}, {"avg_estimated_net_pct": -110},
        ):
            with self.subTest(changed=changed):
                r = example_report()
                r["groups"]["attack"]["3"].update(changed)
                q = assess_observed_quality(r, "2026-11-18", market_open=True)
                self.assertEqual(q["status"], "INSUFFICIENT_EVIDENCE")

    def test_fixed_radar_module_calls_health_guard_after_history_frozen(self):
        code = Path("scripts/update_system.py").read_text(encoding="utf-8")
        self.assertIn("annotate_public_feed(out,observed_report,today_iso,market_open=market_open)", code)
        self.assertLess(code.index("history=update_history("),
                        code.index("annotate_public_feed(out,observed_report"))
        self.assertLess(code.index("annotate_public_feed(out,observed_report"),
                        code.index("OUT.write_text(json.dumps(out"))
        self.assertIn("remote/pick_validation.json", code)

    def test_no_strategy_scores_are_retrained_or_rewritten_from_test_set(self):
        feed = example_feed()
        original = copy.deepcopy(feed)
        q = annotate_public_feed(feed, example_report(), "2026-11-18")
        self.assertEqual(feed["attack"][0]["score"], original["attack"][0]["score"])
        self.assertEqual(feed["next"][0]["score"], original["next"][0]["score"])
        self.assertEqual(feed["monster"][0]["score"], original["monster"][0]["score"])
        self.assertEqual(q["source"], "forward_official_close_pick_validation")
        self.assertNotIn("new_optimized_weight", json.dumps(feed))


if __name__ == "__main__":
    unittest.main()
