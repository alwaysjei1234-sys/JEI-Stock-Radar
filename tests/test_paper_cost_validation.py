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

if __name__=="__main__":
    unittest.main()
