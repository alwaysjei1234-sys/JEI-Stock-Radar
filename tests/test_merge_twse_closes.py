import json
import tempfile
import unittest
from pathlib import Path
from scripts.merge_twse_closes import merge

class MergeTests(unittest.TestCase):
    def test_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            paths=[]
            for index,day in enumerate(("2026-09-30","2026-10-01")):
                path=Path(directory)/str(index)
                data={"code":"2330","market":"TWSE","source":"TWSE STOCK_DAY",
                      "prices":[{"date":day,"close":100+index}]}
                path.write_text(json.dumps(data),encoding="utf-8")
                paths.append(path)
            result=merge(paths)
            self.assertEqual(len(result["2330"]),2)
            with self.assertRaises(ValueError):
                merge(paths+paths[:1])

if __name__=="__main__":
    unittest.main()
