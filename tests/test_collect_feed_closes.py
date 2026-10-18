import json
import tempfile
import unittest
from pathlib import Path
from scripts.collect_feed_closes import collect

class FeedPriceCollectionTests(unittest.TestCase):
    def test_collect_and_sort(self):
        with tempfile.TemporaryDirectory() as d:
            for day,close in [("2026-10-17",101),("2026-10-16",100)]:
                payload={"data_date":day,
                    "source":"remote/system.json.price (feed snapshot; official close not independently confirmed)",
                    "prices":{"2330":{"date":day,"close":close}}}
                (Path(d)/f"{day}.json").write_text(json.dumps(payload),encoding="utf-8")
            self.assertEqual([p["close"] for p in collect(d)["2330"]],[100,101])

    def test_reject_invalid_close(self):
        with tempfile.TemporaryDirectory() as d:
            day="2026-10-16"
            payload={"data_date":day,
                "source":"official close not independently confirmed",
                "prices":{"2330":{"date":day,"close":float("nan")}}}
            (Path(d)/(day+".json")).write_text(json.dumps(payload),encoding="utf-8")
            with self.assertRaises(ValueError):
                collect(d)

    def test_reject_conflicted_symbol(self):
        with tempfile.TemporaryDirectory() as d:
            day="2026-10-16"
            payload={"data_date":day,
                "source":"official close not independently confirmed",
                "conflict_codes":["2330"],
                "prices":{"2330":{"date":day,"close":100}}}
            (Path(d)/(day+".json")).write_text(json.dumps(payload),encoding="utf-8")
            with self.assertRaises(ValueError):
                collect(d)

    def test_reject_wrong_date(self):
        with tempfile.TemporaryDirectory() as d:
            payload={"data_date":"2026-10-16",
                "source":"official close not independently confirmed",
                "prices":{"2330":{"date":"2026-10-17","close":100}}}
            (Path(d)/"2026-10-16.json").write_text(json.dumps(payload),encoding="utf-8")
            with self.assertRaises(ValueError):
                collect(d)

if __name__=="__main__":
    unittest.main()
