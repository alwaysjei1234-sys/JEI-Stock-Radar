import json
import unittest
from pathlib import Path

class StrategyPageSmoke(unittest.TestCase):
    def test_strategy_page_has_controls_and_safe_render(self):
        html=Path("remote/strategy.html").read_text(encoding="utf-8")
        self.assertIn('id="horizon"',html)
        self.assertIn('id="results"',html)
        self.assertIn('paper-leaderboard.json',html)
        self.assertIn("report.verified===true",html)
        self.assertIn("r.matured>=10",html)
        self.assertIn("r.paired_count>=10",html)
        self.assertIn("textContent",html)

    def test_published_seed_is_explicitly_unverified(self):
        payload=json.loads(Path("remote/paper-leaderboard.json").read_text(encoding="utf-8"))
        self.assertIs(payload["verified"],False)
        self.assertEqual(set(payload["horizons"]),{"3","7","15","30","60"})
        for rows in payload["horizons"].values():
            self.assertEqual(len(rows),3)
            for row in rows:
                self.assertIsNone(row["win_rate_pct"])
                self.assertIsNone(row["mean_net_return_pct"])

if __name__=="__main__":
    unittest.main()
