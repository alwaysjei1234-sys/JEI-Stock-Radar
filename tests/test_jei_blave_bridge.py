import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.jei_blave_bridge import evaluate_blave_export, parse_jsonl


def archive():
    days = {}
    dates = ["2026-10-13", "2026-10-14", "2026-10-15",
             "2026-10-16", "2026-10-19", "2026-10-20"]
    for i, day in enumerate(dates):
        # Synthetic data only: never presented as actual exchange history.
        quotes = {str(1000 + n): 40.0 for n in range(500)}
        quotes["2330"] = [100, 101, 105, 110, 115, 120][i]
        days[day] = quotes
    return {"schema": 1, "kind": "official_daily_close", "days": days}


def signal(**changes):
    row = {"signal_id": "blave-fixture-001",
           "generated_at": "2026-10-13T14:01:00+08:00",
           "ticker": "2330", "market": "TW",
           "strategy_id": "sma20_60", "signal": "BUY",
           "reference_price": 100, "data_asof": "2026-10-13",
           "source": "blave-agent"}
    row.update(changes)
    return row


class BlaveOfflineBridgeTests(unittest.TestCase):
    def test_reuses_jei_next_session_costed_forward_engine(self):
        result = evaluate_blave_export([signal()], archive())
        self.assertEqual(result["status"], "OBSERVED_PROXY_ONLY")
        self.assertFalse(result["external_connection_active"])
        self.assertFalse(result["independent_oos_verified"])
        self.assertEqual(result["scored_buy_signals"], 1)
        item = result["observations"][0]
        self.assertEqual(item["entry_date"], "2026-10-14")
        self.assertEqual(item["entry_rule"], "next_session_close_proxy")
        outcome = item["outcomes"]["3"]
        self.assertEqual(outcome["status"], "mature")
        self.assertEqual(outcome["exit_date"], "2026-10-19")
        self.assertLess(outcome["net_return_pct"], outcome["gross_return_pct"])
        self.assertGreater(outcome["net_return_pct"], 0)
        self.assertIsNone(result["strategies"]["sma20_60"]["30"]["win_rate_pct"])
        self.assertEqual(result["strategies"]["sma20_60"]["30"]["pending"], 1)

    def test_rejects_duplicate_strategy_day_symbol_and_signal_id(self):
        for second in (signal(signal_id="blave-fixture-002"),
                       signal(signal="SELL", reference_price=100)):
            with self.subTest(second=second), self.assertRaisesRegex(ValueError, "duplicate"):
                evaluate_blave_export([signal(), second], archive())

    def test_post_close_time_timezone_and_lookahead_guard(self):
        for changes in (
            {"generated_at": "2026-10-13T13:29:00+08:00"},
            {"generated_at": "2026-10-13T06:00:00Z"},
            {"generated_at": "2026-10-13T14:05:00"},
            {"generated_at": "2026-10-14T14:01:00+08:00"},
            {"data_asof": "2026-10-14"},
            {"data_asof": "2026-10-21"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                evaluate_blave_export([signal(**changes)], archive())

    def test_rejects_wrong_price_market_and_invalid_tickers(self):
        for changes in (
            {"reference_price": 99},
            {"reference_price": float("nan")},
            {"reference_price": True},
            {"market": "US"},
            {"source": "untrusted_feed"},
            {"ticker": "AAPL"},
            {"ticker": "fake$"},
            {"signal": "SHORT"},
        ):
            with self.subTest(changes=changes), self.assertRaises((ValueError, TypeError)):
                evaluate_blave_export([signal(**changes)], archive())

    def test_missing_official_session_or_incomplete_coverage_fail_closed(self):
        a = archive()
        del a["days"]["2026-10-15"]
        with self.assertRaisesRegex(ValueError, "skipped exchange session"):
            evaluate_blave_export([signal()], a)
        b = archive()
        b["days"]["2026-10-14"] = {"2330": 101}
        with self.assertRaisesRegex(ValueError, "incomplete official-close session"):
            evaluate_blave_export([signal()], b)

    def test_non_buy_signals_not_included_in_win_rate(self):
        result = evaluate_blave_export([signal(signal="HOLD")], archive())
        self.assertEqual(result["scored_buy_signals"], 0)
        self.assertEqual(result["input_signals"], 1)
        self.assertEqual(result["strategies"], {})
        self.assertEqual(result["not_scored_non_buy_signals"][0]["reason"], "non_buy_not_scored")

    def test_bounded_jsonl_and_cli_rejection_receipt(self):
        a = archive()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            prices = home / "close.json"
            signals = home / "blave.jsonl"
            out = home / "audit.json"
            prices.write_text(json.dumps(a), encoding="utf-8")
            signals.write_text(json.dumps(signal()) + "\n", encoding="utf-8")
            cmd = [sys.executable, "-m", "tools.jei_blave_bridge",
                   "--signals", str(signals), "--prices", str(prices), "--out", str(out)]
            good = subprocess.run(cmd, text=True, capture_output=True, check=False)
            self.assertEqual(good.returncode, 0, good.stderr)
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(report["scored_buy_signals"], 1)
            signals.write_text("{not-json\n", encoding="utf-8")
            bad = subprocess.run(cmd, text=True, capture_output=True, check=False)
            self.assertEqual(bad.returncode, 1)
            receipt = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "REJECTED")
            self.assertEqual(receipt["external_connection_active"], False)
        with self.assertRaisesRegex(ValueError, "oversized"):
            parse_jsonl(" " * 4097 + "\n")


if __name__ == "__main__":
    unittest.main()
