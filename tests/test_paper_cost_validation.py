import unittest
from scripts.forward_pick_score import score_pick

class CostValidationTests(unittest.TestCase):
    def test_reject_invalid_cost_inputs(self):
        pick={"code":"2330","cohort":"momentum","as_of":"2026-10-12"}
        for name,value in (("fee_rate",-0.1),("sell_tax_rate",float("nan")),
                           ("slippage_rate",float("inf")),("fee_rate",True)):
            with self.subTest(name=name,value=value):
                with self.assertRaises(ValueError):
                    score_pick(pick,[],**{name:value})

    def test_reject_combined_selling_cost_over_100_percent(self):
        pick={"code":"2330","cohort":"momentum","as_of":"2026-10-12"}
        with self.assertRaises(ValueError):
            score_pick(pick,[],fee_rate=0.4,sell_tax_rate=0.4,slippage_rate=0.3)

if __name__=="__main__":
    unittest.main()
