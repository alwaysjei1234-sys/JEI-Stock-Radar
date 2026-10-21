import unittest
from datetime import date
from scripts.backfill_twse_ohlcv import target_months, run

class BackfillCalendarTests(unittest.TestCase):
    def test_three_months_cross_year(self):
        self.assertEqual(target_months(date(2026,1,20)),['202511','202512','202601'])
    def test_three_months_regular(self):
        self.assertEqual(target_months(date(2026,10,20)),['202608','202609','202610'])

    def test_not_ready_feed_skips_downloads(self):
        import json, tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"system.json"
            source.write_text(json.dumps({"patterns":{"status":"insufficient"}}),encoding="utf-8")
            with patch("scripts.backfill_twse_ohlcv.fetch_month") as fetch:
                self.assertEqual(run(source,Path(directory)/"candles"),0)
                fetch.assert_not_called()

    def test_prioritizes_uncovered_codes_when_date_does_not_change(self):
        import json, tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            source=base/"system.json"
            codes=["2328","2377","3005"]
            source.write_text(json.dumps({"patterns":{"status":"ready","data_date":"2026-10-20",
                "signals":{"breakout":[{"code":code} for code in codes]}}}),encoding="utf-8")
            cache=base/"candles"
            cache.mkdir()
            for month in target_months(date(2026,10,20)):
                (cache/f"2328-{month}.json").write_text(json.dumps({
                    "code":"2328","market":"TWSE","adjusted_for_corporate_actions":False,
                    "ohlcv_units":{"volume":"shares"},"ohlcv":[{"date":"2026-10-20"}]}),encoding="utf-8")
            def fake_fetch(code,month):
                return {"code":code,"market":"TWSE","adjusted_for_corporate_actions":False,
                    "ohlcv_units":{"volume":"shares"},"ohlcv":[{"date":"2026-10-20"}]}
            with patch("scripts.backfill_twse_ohlcv.fetch_month",side_effect=fake_fetch) as fetch, patch("scripts.backfill_twse_ohlcv.time.sleep"):
                self.assertEqual(run(source,cache,max_codes=2,pause=3),6)
                self.assertEqual({call.args[0] for call in fetch.call_args_list},{"2377","3005"})

    def test_refreshes_stale_current_month_but_preserves_older_months(self):
        import json, tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            source=base/"system.json"
            source.write_text(json.dumps({"patterns":{"status":"ready",
                "data_date":"2026-10-21","signals":{"a":[{"code":"2328"}]}}}),encoding="utf-8")
            cache=base/"candles"
            cache.mkdir()
            def payload(month,day):
                return {"code":"2328","market":"TWSE",
                    "adjusted_for_corporate_actions":False,
                    "ohlcv_units":{"volume":"shares"},
                    "ohlcv":[{"date":day,"close":50.9}]}
            for month in target_months(date(2026,10,21)):
                day="2026-10-20" if month=="202610" else "2026-09-01"
                (cache/f"2328-{month}.json").write_text(json.dumps(payload(month,day)),encoding="utf-8")
            with patch("scripts.backfill_twse_ohlcv.fetch_month",
                       return_value=payload("202610","2026-10-21")) as fetch:
                self.assertEqual(run(source,cache,max_codes=1,pause=3),1)
                fetch.assert_called_once_with("2328","202610")
            refreshed=json.loads((cache/"2328-202610.json").read_text(encoding="utf-8"))
            self.assertEqual(refreshed["ohlcv"][-1]["date"],"2026-10-21")

if __name__=='__main__':unittest.main()
