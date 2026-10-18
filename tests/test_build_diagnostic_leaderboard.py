import tempfile
import unittest
from pathlib import Path
from scripts.build_diagnostic_leaderboard import build

class DiagnosticLeaderboardTests(unittest.TestCase):
    def test_empty_archive_never_claims_verified_returns(self):
        with tempfile.TemporaryDirectory() as directory:
            picks=Path(directory)/"picks"
            prices=Path(directory)/"prices"
            picks.mkdir()
            prices.mkdir()
            result=build(picks,prices)
            self.assertFalse(result["verified"])
            self.assertEqual(result["data_quality"]["sample_count"],0)
            for rows in result["horizons"].values():
                for row in rows:
                    self.assertIsNone(row["mean_net_return_pct"])

if __name__=="__main__":
    unittest.main()
