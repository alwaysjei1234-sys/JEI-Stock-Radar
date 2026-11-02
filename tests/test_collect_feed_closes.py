import json
import copy
import tempfile
import unittest
from pathlib import Path
from scripts.collect_feed_closes import collect
from scripts.export_official_closes import export_archive

class FeedPriceCollectionTests(unittest.TestCase):
    def official(self, day='2026-10-22'):
        return export_archive({'schema': 1, 'kind': 'official_daily_close',
            'days': {day: {str(1000+i): 100+i/100 for i in range(600)}}}, day)

    def test_official_export_and_recovered_source_are_diagnostic_compatible(self):
        with tempfile.TemporaryDirectory() as directory:
            day='2026-10-22'; payload=self.official(day)
            path=Path(directory)/(day+'.json')
            for source in (payload['source'],
                    'remote/daily_prices.json preserved in same-day 2026-10-22 market feed commit f40ced6e; official daily close'):
                payload['source']=source
                path.write_text(json.dumps(payload))
                self.assertEqual(collect(directory)['1000'], [{'date': day, 'close': 100}])

    def test_malformed_official_export_does_not_silently_drop_prices(self):
        with tempfile.TemporaryDirectory() as directory:
            good=self.official(); day=good['data_date']; path=Path(directory)/(day+'.json')
            cases=[]
            for key,value in (('source','untrusted'),('schema',True),('coverage_count',599),
                              ('days',{'2026-10-23':good['days'][day]})):
                bad=copy.deepcopy(good); bad[key]=value; cases.append(bad)
            for price in (True, float('nan'),float('inf'),0):
                bad=copy.deepcopy(good);bad['days'][day]['1000']=price;cases.append(bad)
            for bad in cases:
                with self.subTest(bad=list(bad)), self.assertRaises(ValueError):
                    path.write_text(json.dumps(bad));collect(directory)

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
