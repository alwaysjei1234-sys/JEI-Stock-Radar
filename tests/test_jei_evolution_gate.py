import unittest
from tools.jei_evolution_gate import evaluate

def example():
    return {
        "proposals": [
            {"role": "researcher", "model_id": "independent-model-a"},
            {"role": "critic", "model_id": "independent-model-b"}
        ],
        "data_provenance": "immutable historical snapshot",
        "backtest_version": "v1",
        "lookahead_detected": False,
        "overlap_removed": True,
        "costs_included": True,
        "baseline": {"oos_trades": 120, "market_regimes": 3, "net_expectancy": 0.02,
                     "win_rate": 0.76, "max_drawdown": 0.18},
        "candidate": {"strategy_id": "candidate-1", "code_commit": "abcdef",
                      "oos_trades": 120, "market_regimes": 3, "net_expectancy": 0.03,
                      "win_rate": 0.81, "max_drawdown": 0.15}
    }

class EvolutionTests(unittest.TestCase):
    def test_valid_candidate_requires_review_not_deploy(self):
        r = evaluate(example())
        self.assertEqual(r["decision"], "REVIEW")
        self.assertFalse(r["auto_deploy"])

    def test_missing_second_model_rejected(self):
        x = example()
        x["proposals"] = x["proposals"][:1]
        self.assertEqual(evaluate(x)["decision"], "REJECT")

    def test_leakage_rejected(self):
        x = example()
        x["lookahead_detected"] = True
        self.assertEqual(evaluate(x)["decision"], "REJECT")

    def test_small_sample_rejected(self):
        x = example()
        x["candidate"]["oos_trades"] = 30
        self.assertEqual(evaluate(x)["decision"], "REJECT")

    def test_worse_drawdown_rejected(self):
        x = example()
        x["candidate"]["max_drawdown"] = 0.2
        self.assertEqual(evaluate(x)["decision"], "REJECT")

    def test_missing_metrics_rejected(self):
        x = example()
        del x["candidate"]["net_expectancy"]
        self.assertEqual(evaluate(x)["decision"], "REJECT")

if __name__ == "__main__":
    unittest.main()
