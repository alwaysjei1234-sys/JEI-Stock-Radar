import tempfile
import json
import unittest
from pathlib import Path
from scripts.build_diagnostic_leaderboard import build
from scripts.export_official_closes import export_archive

class DiagnosticLeaderboardTests(unittest.TestCase):
    def test_mixed_archive_can_publish_without_upgrading_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            picks=Path(directory)/'picks';prices=Path(directory)/'prices'
            picks.mkdir();prices.mkdir()
            day='2026-10-21'
            (picks/(day+'.json')).write_text(json.dumps({'data_date':day,'picks':[
                {'as_of':day,'code':'1000','cohort':'momentum'}]}))
            (prices/(day+'.json')).write_text(json.dumps({'data_date':day,
                'source':'official close not independently confirmed',
                'prices':{'1000':{'date':day,'close':100}}}))
            day='2026-10-22'
            official=export_archive({'schema':1,'kind':'official_daily_close',
                'days':{day:{str(1000+i):101 for i in range(600)}}},day)
            (prices/(day+'.json')).write_text(json.dumps(official))
            result=build(picks,prices)
            self.assertEqual(result['price_data_date'],day)
            self.assertEqual(result['data_quality']['sample_count'],1)
            self.assertFalse(result['verified'])
            self.assertFalse(result['data_quality']['verified_by_system'])
            for rows in result['horizons'].values():
                for row in rows:self.assertIsNone(row['mean_net_return_pct'])

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
