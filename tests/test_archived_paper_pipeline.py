import json
import tempfile
import unittest
from pathlib import Path
from scripts.run_archived_paper_pipeline import run

class ArchivedPipelineTests(unittest.TestCase):
    def test_end_to_end_with_archived_observations(self):
        with tempfile.TemporaryDirectory() as root:
            picks_dir=Path(root)/"picks"
            prices_dir=Path(root)/"prices"
            picks_dir.mkdir()
            prices_dir.mkdir()
            day="2026-10-16"
            (picks_dir/f"{day}.json").write_text(json.dumps({
                "data_date":day,"picks":[{"as_of":day,"code":"2330","cohort":"momentum"}]}),encoding="utf-8")
            for date,price in [("2026-10-16",100),("2026-10-19",102)]:
                (prices_dir/f"{date}.json").write_text(json.dumps({
                    "data_date":date,
                    "source":"remote/system.json.price (feed snapshot; official close not independently confirmed)",
                    "prices":{"2330":{"date":date,"close":price}}}),encoding="utf-8")
            report=run(picks_dir,prices_dir)
            self.assertEqual(report["sample_count"],1)
            self.assertEqual(report["picks"][0]["entry_price"],102)
            self.assertFalse(report["data_quality"]["official_close_verified"])
            self.assertEqual(report["picks"][0]["outcomes"]["3"]["status"],"pending")

if __name__=="__main__":
    unittest.main()
