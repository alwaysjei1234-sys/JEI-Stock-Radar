import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.jei_dqn_oos_bridge import evaluate_dqn_export


def archive():
    days = {}
    for i, day in enumerate(("2026-10-13","2026-10-14","2026-10-15",
                              "2026-10-16","2026-10-19","2026-10-20")):
        quotes = {str(1000 + n): 50.0 for n in range(500)}
        quotes["2330"] = [100.0, 101.0, 105.0, 110.0, 115.0, 120.0][i]
        days[day] = quotes
    return {"schema": 1, "kind": "official_daily_close", "days": days}


def signal(**kw):
    row = {"signal_id": "dqn-20261014-2330", "strategy_id": "dqn_v1",
           "ticker": "2330", "market": "TW", "signal": "BUY",
           "generated_at": "2026-10-14T14:03:00+08:00",
           "data_asof": "2026-10-14", "reference_price": 101.0,
           "source": "dqn-experiment", "split": "oos",
           "model_version": "checkpoint_01", "trained_through": "2026-10-13"}
    row.update(kw)
    return row


class DqnEvidenceBridgeTests(unittest.TestCase):
    def test_oos_only_scores_with_jei_forward_cost_engine(self):
        train = signal(signal_id="dqn-train-20261013",data_asof="2026-10-13",
                       generated_at="2026-10-13T13:40:00+08:00",
                       reference_price=100,split="train")
        report = evaluate_dqn_export([train, signal()], archive())
        self.assertEqual(report["status"], "OBSERVED_PROXY_ONLY")
        self.assertEqual(report["train_rows_excluded"], 1)
        self.assertEqual(report["oos_rows"], 1)
        self.assertFalse(report["model_training_verified"])
        self.assertFalse(report["independent_oos_verified"])
        self.assertEqual(report["scored_buy_signals"], 1)
        obs = report["observations"][0]
        self.assertEqual(obs["entry_date"], "2026-10-15")
        self.assertEqual(obs["entry_rule"], "next_session_close_proxy")
        self.assertGreater(obs["outcomes"]["3"]["net_return_pct"], 0)
        self.assertLess(obs["outcomes"]["3"]["net_return_pct"],
                        obs["outcomes"]["3"]["gross_return_pct"])

    def test_in_sample_signal_cannot_be_scored_as_oos(self):
        with self.assertRaisesRegex(ValueError, "inside its declared training"):
            evaluate_dqn_export([signal(trained_through="2026-10-14")], archive())

    def test_train_only_has_no_measured_oos_result(self):
        data = signal(signal_id="dqn-train",split="train",data_asof="2026-10-13",
                      generated_at="2026-10-13T14:01:00+08:00",reference_price=100)
        report = evaluate_dqn_export([data], archive())
        self.assertEqual(report["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(report["oos_rows"], 0)

    def test_reject_model_retraining_under_same_version(self):
        other = signal(signal_id="dqn-20261015-2330",data_asof="2026-10-15",
                       generated_at="2026-10-15T14:01:00+08:00",
                       reference_price=105,trained_through="2026-10-14")
        with self.assertRaisesRegex(ValueError, "silently changed training cutoff"):
            evaluate_dqn_export([signal(), other], archive())

    def test_explicit_split_model_and_origin_required(self):
        for edits in ({"split": ""}, {"split": "validation"}, {"model_version": ""},
                      {"trained_through": "2026-10-15"}, {"source": "blave-agent"},
                      {"generated_at": "2026-10-14T12:30:00+08:00"}):
            with self.subTest(edits=edits), self.assertRaises((ValueError, TypeError)):
                evaluate_dqn_export([signal(**edits)], archive())

    def test_reject_duplicate_oos_and_train_rows(self):
        one = signal()
        two = signal(signal_id="dqn-extra")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            evaluate_dqn_export([one,two], archive())

    def test_cli_saves_rejection_receipt_and_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/"dqn.jsonl";prices=root/"prices.json";out=root/"result.json"
            prices.write_text(json.dumps(archive()),encoding="utf-8")
            cmd=[sys.executable,"-m","tools.jei_dqn_oos_bridge",
                 "--actions",str(path),"--prices",str(prices),"--out",str(out)]
            path.write_text(json.dumps(signal())+"\n",encoding="utf-8")
            good=subprocess.run(cmd,text=True,capture_output=True,check=False)
            self.assertEqual(good.returncode,0,good.stderr)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["oos_rows"],1)
            path.write_text(json.dumps(signal(trained_through="2026-10-14"))+"\n",encoding="utf-8")
            bad=subprocess.run(cmd,text=True,capture_output=True,check=False)
            self.assertEqual(bad.returncode,1)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["status"],"REJECTED")


if __name__=="__main__":
    unittest.main()
