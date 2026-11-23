"""Offline synthetic bridge tests; no upstream model calls."""
import unittest
from datetime import date
from tools.jei_tradingagents_bridge import build_candidate, run_review, _symbol


def archive(day="2026-11-03"):
    prices = {str(1000 + n): 10 + n / 100 for n in range(510)}
    prices["1101"] = 27.7
    return {"schema": 1, "kind": "official_daily_close", "days": {day: prices}}


def candidate():
    return build_candidate(archive(), "1101", "TWSE", "2026-11-03",
                           today=date(2026, 11, 23))


class FakeGraph:
    def __init__(self, **kwargs):
        self.args = kwargs
    def propagate(self, ticker, day):
        return {"market_report": "Technical note", "final_trade_decision": "BUY"}, "Buy"


class BridgeTests(unittest.TestCase):
    def test_taiwan_symbol_and_dated_close(self):
        row = candidate()
        self.assertEqual(row["ticker"], "1101.TW")
        self.assertEqual(row["dated_jei_close"], 27.7)
        self.assertEqual(_symbol("1101", "TPEx"), "1101.TWO")

    def test_dry_run_blocks_network_and_orders(self):
        row = run_review(candidate())
        self.assertEqual(row["status"], "DRY_RUN")
        for field in ("external_model_called", "actionable_signal",
                      "auto_order", "auto_promote", "independent_market_confirmation"):
            self.assertFalse(row[field])

    def test_reject_unapproved_providers_and_missing_opt_in(self):
        for env in ({}, {"JEI_ENABLE_EXTERNAL_AI_RESEARCH": "1"},
                    {"JEI_ENABLE_EXTERNAL_AI_RESEARCH": "1",
                     "TRADINGAGENTS_LLM_PROVIDER": "openai"}):
            with self.subTest(env=env), self.assertRaises(ValueError):
                run_review(candidate(), execute=True, environ=env,
                           graph_factory=FakeGraph, default_config={})

    def test_mock_model_is_research_only_even_on_buy(self):
        r = run_review(candidate(), execute=True,
                       environ={"JEI_ENABLE_EXTERNAL_AI_RESEARCH": "1",
                                "TRADINGAGENTS_LLM_PROVIDER": "ollama"},
                       graph_factory=FakeGraph, default_config={})
        self.assertEqual(r["status"], "UNVERIFIED_EXTERNAL_RESEARCH")
        self.assertEqual(r["model_rating_unverified"], "Buy")
        self.assertIn("technical", r["agent_review"])
        self.assertFalse(r["actionable_signal"])
        self.assertFalse(r["auto_order"])

    def test_private_fields_and_forged_trust_are_rejected(self):
        for field in ("holdings", "api_key", "portfolio"):
            c = candidate()
            c[field] = {"private": 1}
            with self.subTest(field=field), self.assertRaises(ValueError):
                run_review(c)
        c = candidate()
        c["live_quote_verified"] = True
        with self.assertRaises(ValueError):
            run_review(c)

    def test_reject_missing_stale_and_invalid_prices(self):
        for price in (True, -1, float("nan"), float("inf"), "27.7"):
            a = archive()
            a["days"]["2026-11-03"]["1101"] = price
            with self.subTest(price=price), self.assertRaises(ValueError):
                build_candidate(a, "1101", "TWSE", "2026-11-03", today=date(2026, 11, 23))
        with self.assertRaises(ValueError):
            build_candidate({"schema": 1, "kind": "official_daily_close", "days": {"2026-11-03": {"1101": 27.7}}},
                            "1101", "TWSE", "2026-11-03", today=date(2026, 11, 23))

    def test_market_security_and_date_controls(self):
        for code, market in (("../1101", "TWSE"), ("1101.TW", "TWSE"),
                             ("1101", "UNKNOWN"), ("1101.TW", "US")):
            with self.subTest(code=code, market=market), self.assertRaises(ValueError):
                build_candidate(archive(), code, market, "2026-11-03",
                                today=date(2026, 11, 23))
        with self.assertRaises(ValueError):
            build_candidate(archive(), "1101", "TWSE", "2026-11-24",
                            today=date(2026, 11, 23))
        with self.assertRaises(ValueError):
            build_candidate(archive(), "1101", "TWSE", "2026-11-04",
                            today=date(2026, 11, 23))


if __name__ == "__main__":
    unittest.main()
