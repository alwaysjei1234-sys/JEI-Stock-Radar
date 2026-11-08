import unittest
from tools.jei_technical_candidate import signal, rsi, ema

class TechnicalCandidateTests(unittest.TestCase):
    def test_short_history_rejected(self):
        with self.assertRaisesRegex(ValueError, "65"):
            signal([100.0] * 30)

    def test_flat_prices_not_signal(self):
        result = signal([100.0] * 90)
        self.assertFalse(result["candidate"])
        self.assertFalse(result["rsi_divergence_proxy_warning"])

    def test_future_bar_cannot_affect_prior_signal(self):
        prices = [100 + (i % 7) - 3 for i in range(90)]
        first = signal(prices)
        extended = prices + [1000]
        self.assertEqual(first, signal(extended[:-1]))

    def test_invalid_prices(self):
        with self.assertRaises(ValueError):
            signal([100] * 89 + [float("nan")])

    def test_rsi_length(self):
        self.assertEqual(len(rsi([100+i for i in range(40)])), 40)

if __name__ == "__main__":
    unittest.main()
