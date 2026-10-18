import json
import tempfile
import unittest
from pathlib import Path
from scripts.collect_pick_snapshots import load_snapshots

class SnapshotCollectionTests(unittest.TestCase):
    def test_collect_in_date_order(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for day,code in [("2026-10-17","2"),("2026-10-16","1")]:
                (root/f"{day}.json").write_text(json.dumps({"data_date":day,"picks":[{"as_of":day,"code":code,"cohort":"monster"}]}),encoding="utf-8")
            self.assertEqual([p["code"] for p in load_snapshots(root)],["1","2"])

    def test_reject_modified_signal_date(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/"2026-10-16.json").write_text(json.dumps({"data_date":"2026-10-16","picks":[{"as_of":"2026-10-17","code":"1","cohort":"monster"}]}),encoding="utf-8")
            with self.assertRaises(ValueError):
                load_snapshots(d)

if __name__=="__main__":
    unittest.main()
