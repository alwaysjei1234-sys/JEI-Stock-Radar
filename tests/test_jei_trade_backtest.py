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

if __name__ == "__main__":
    unittest.main()
