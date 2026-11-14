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

if __name__ == "__main__":
    unittest.main()
