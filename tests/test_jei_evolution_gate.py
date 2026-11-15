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

    def test_required_roles_must_have_distinct_model_ids(self):
        for proposals in (
            [{"role": "researcher", "model_id": "model-a"},
             {"role": "critic", "model_id": "model-a"},
             {"role": "observer", "model_id": "model-b"}],
            [{"role": "researcher", "model_id": "model-a"},
             {"role": "critic"},
             {"role": "researcher", "model_id": "model-b"}],
            [{"role": "researcher", "model_id": "model-a"},
             {"role": "critic", "model_id": " model-a "}],
        ):
            with self.subTest(proposals=proposals):
                bundle = {**example(), "proposals": proposals}
                result = evaluate(bundle)
                self.assertEqual(result["decision"], "REJECT")
                self.assertIn("need_independent_researcher_and_critic_models", result["reasons"])

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

    def test_invalid_metric_values_cannot_reach_review(self):
        for label, key, value in (
            ("candidate", "net_expectancy", float("nan")),
            ("baseline", "net_expectancy", float("-inf")),
            ("candidate", "win_rate", 1.1),
            ("candidate", "max_drawdown", -0.1),
            ("candidate", "oos_trades", 100.5),
            ("candidate", "market_regimes", 4.5),
            ("baseline", "market_regimes", 121),
        ):
            with self.subTest(label=label, key=key, value=value):
                bundle = example()
                bundle[label][key] = value
                result = evaluate(bundle)
                self.assertEqual(result["decision"], "REJECT")
                self.assertIn(f"{label}_invalid_{key}", result["reasons"])

if __name__ == "__main__":
    unittest.main()
