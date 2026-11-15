import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from tools.jei_trade_backtest import evaluate

def trade(ticker, entry, exit, ret, regime="bull", split="oos"):
    return dict(strategy_id="candidate", ticker=ticker, entry_date=entry,
                exit_date=exit, gross_return=str(ret), regime=regime, split=split)

class BacktestEvidenceTests(unittest.TestCase):
    def test_cost_adjusted_metrics(self):
        rows = [trade("2330", "2026-01-01", "2026-01-03", .04),
                trade("2317", "2026-01-01", "2026-01-03", -.01, "bear")]
        m = evaluate(rows, .01)["candidate"]
        self.assertEqual(m["oos_trades"], 2)
        self.assertAlmostEqual(m["win_rate"], .5)
        self.assertAlmostEqual(m["net_expectancy"], .005)
        self.assertEqual(m["market_regimes"], 2)

    def test_parallel_trades_do_not_invent_portfolio_equity(self):
        first = trade("2330", "2026-01-01", "2026-01-03", .20)
        second = trade("2317", "2026-01-02", "2026-01-03", -.10)
        third = trade("2308", "2026-01-03", "2026-01-06", -.05)
        for rows in ([first, second, third], [second, third, first]):
            with self.subTest(rows=rows):
                result = evaluate(rows, 0)["candidate"]
                self.assertIsNone(result["max_drawdown"])
                self.assertIsNone(result["net_compounded_return"])
                self.assertEqual(result["drawdown_basis"],
                                 "unavailable_overlapping_positions_without_capital_weights")
                self.assertEqual(result["oos_trades"], 3)

    def test_nonoverlapping_trades_compound_in_exit_order(self):
        first = trade("2330", "2026-01-01", "2026-01-03", .20)
        second = trade("2317", "2026-01-03", "2026-01-05", -.10)
        third = trade("2308", "2026-01-05", "2026-01-06", -.05)
        for rows in ([first, second, third], [second, third, first]):
            with self.subTest(rows=rows):
                result = evaluate(rows, 0)["candidate"]
                self.assertAlmostEqual(result["max_drawdown"], 1 - .90 * .95)
                self.assertAlmostEqual(result["net_compounded_return"],
                                       1.20 * .90 * .95 - 1)

    def test_total_loss_does_not_create_negative_equity_or_recover(self):
        first = trade("2330", "2026-01-01", "2026-01-03", -1)
        same_exit = trade("2317", "2026-01-02", "2026-01-03", -1)
        later = trade("2308", "2026-01-03", "2026-01-06", .5)
        sequential = evaluate([first, later], .01)["candidate"]
        self.assertAlmostEqual(sequential["max_drawdown"], 1)
        self.assertAlmostEqual(sequential["net_compounded_return"], -1)
        parallel = evaluate([first, same_exit, later], .01)["candidate"]
        self.assertIsNone(parallel["max_drawdown"])
        self.assertIsNone(parallel["net_compounded_return"])
        self.assertAlmostEqual(parallel["net_expectancy"], (-2 + .49) / 3)

    def test_parallel_winner_and_loser_do_not_imply_full_capital_loss(self):
        rows = [trade("2330", "2026-01-01", "2026-01-03", 1),
                trade("2317", "2026-01-02", "2026-01-03", -1)]
        result = evaluate(rows, 0)["candidate"]
        self.assertAlmostEqual(result["win_rate"], .5)
        self.assertAlmostEqual(result["net_expectancy"], 0)
        self.assertIsNone(result["max_drawdown"])
        self.assertIsNone(result["net_compounded_return"])

    def test_overlap_rejected(self):
        rows = [trade("2330", "2026-01-01", "2026-01-05", .03),
                trade("2330", "2026-01-04", "2026-01-07", .02)]
        with self.assertRaisesRegex(ValueError, "overlapping"):
            evaluate(rows, .005)

    def test_train_excluded(self):
        rows = [trade("2330", "2026-01-01", "2026-01-03", .5, split="train"),
                trade("2330", "2026-02-01", "2026-02-03", .01)]
        self.assertEqual(evaluate(rows, .005)["candidate"]["oos_trades"], 1)

    def test_invalid_cost_rejected(self):
        with self.assertRaises(ValueError):
            evaluate([], -0.01)

    def test_no_oos_evidence(self):
        rows = [trade("2330", "2026-01-01", "2026-01-03", .5, split="train")]
        self.assertEqual(evaluate(rows, .01), {})

    def test_cli_reports_train_only_as_insufficient_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "trades.csv"
            output = Path(tmp) / "metrics.json"
            row = trade("2330", "2026-01-01", "2026-01-03", .5, split="train")
            for split, status, returncode in (
                ("train", "INSUFFICIENT_EVIDENCE", 1),
                ("oos", "CALCULATED", 0),
            ):
                with self.subTest(split=split):
                    with source.open("w", encoding="utf-8", newline="") as handle:
                        writer = csv.DictWriter(handle, fieldnames=list(row))
                        writer.writeheader()
                        writer.writerow({**row, "split": split})
                    run = subprocess.run(
                        [sys.executable, "-m", "tools.jei_trade_backtest",
                         "--trades", str(source), "--cost", ".01", "--out", str(output)],
                        capture_output=True, text=True, check=False,
                    )
                    report = json.loads(output.read_text(encoding="utf-8"))
                    self.assertEqual(run.returncode, returncode)
                    self.assertEqual(report["status"], status)
                    self.assertFalse(report["walk_forward_verified"])
                    self.assertFalse(report["lookahead_verified"])
                    if split == "train":
                        self.assertEqual(report["reason"], "no_oos_trades")
                        self.assertEqual(report["metrics"], {})
                    else:
                        self.assertEqual(report["metrics"]["candidate"]["oos_trades"], 1)

    def test_cli_rejects_malformed_csv_with_a_json_receipt(self):
        header = "strategy_id,ticker,entry_date,exit_date,regime,split,gross_return"
        row = "candidate,2330,2026-01-01,2026-01-03,bull,oos,0.04"
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "trades.csv"
            output = Path(tmp) / "metrics.json"
            for fields, values, reason in (
                (header, row.rsplit(",", 1)[0], "invalid_csv_row_2"),
                (header, row + ",extra", "invalid_csv_row_2"),
                (header + ",gross_return", row + ",0.99", "duplicate_csv_columns"),
            ):
                with self.subTest(reason=reason, values=values):
                    output.unlink(missing_ok=True)
                    source.write_text(fields + "\n" + values + "\n", encoding="utf-8")
                    run = subprocess.run(
                        [sys.executable, "-m", "tools.jei_trade_backtest",
                         "--trades", str(source), "--cost", ".01", "--out", str(output)],
                        capture_output=True, text=True, check=False,
                    )
                    self.assertEqual(run.returncode, 1)
                    self.assertTrue(output.exists(), run.stderr)
                    report = json.loads(output.read_text(encoding="utf-8"))
                    self.assertEqual(report, {"status": "REJECT", "reason": reason, "metrics": {}})

if __name__ == "__main__":
    unittest.main()
