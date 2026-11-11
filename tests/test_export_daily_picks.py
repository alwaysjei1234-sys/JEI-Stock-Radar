import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from scripts.export_daily_picks import extract, first_close_snapshot

class DailyPickExportTests(unittest.TestCase):
    def test_archive_uses_first_verified_same_day_publication(self):
        day = "2026-11-11"
        archive = {"schema": 1, "kind": "official_daily_close", "days": {
            day: {str(1000 + n): 100.0 for n in range(600)}
        }}
        def source(sha, stamp, committed, code, stale=False):
            return {"sha": sha, "blob": "blob-" + sha, "committed_at": committed,
                    "feed": {"data_date": day, "updated_at": stamp,
                             "market": {"mode": "今日收盤", "stale": stale, "close_count": 600},
                             "holdings": {}, "attack": [{"code": code, "score": 90, "price": 100}]}}
        snapshots = [
            source("stale", day + " 13:40", day + "T13:41:00+08:00", "1000", stale=True),
            source("future-clock", day + " 15:40", day + "T13:50:00+08:00", "1001"),
            source("first", day + " 14:10", day + "T14:12:00+08:00", "1002"),
            source("later", day + " 16:00", day + "T16:01:00+08:00", "1003"),
        ]
        now = datetime(2026, 11, 11, 19, tzinfo=ZoneInfo("Asia/Taipei"))
        result = first_close_snapshot(day, archive, snapshots, now, 10)
        self.assertEqual(result["picks"][0]["code"], "1002")
        self.assertEqual(result["source_commit"], "first")
        self.assertEqual(result["source_blob"], "blob-first")
        with self.assertRaises(ValueError):
            first_close_snapshot(day, archive, snapshots[:2], now, 10)

    def test_actual_feed_cohort_mapping_and_date(self):
        feed={"data_date":"2026-10-16","market":{"last_checked_at":"2026-10-18 08:47"},
              "attack":[{"code":"2330","name":"A","score":80}],
              "monster":[{"code":"1234","name":"B","score":99}],
              "future_monster":[{"code":"2609","name":"C","score":82}]}
        result=extract(feed)
        self.assertEqual(result["data_date"],"2026-10-16")
        self.assertEqual([p["cohort"] for p in result["picks"]],
                         ["momentum","monster","pre_breakout"])
        self.assertEqual(result["picks"][2]["as_of"],"2026-10-16")

    def test_limit_and_dedup(self):
        feed={"data_date":"2026-10-16","monster":[{"code":"1"},{"code":"1"},{"code":"2"}]}
        rows=extract(feed,limit=2)["picks"]
        self.assertEqual([p["code"] for p in rows],["1","2"])

    def test_skip_malformed_feed_rows(self):
        feed={"data_date":"2026-10-16","attack":[None,42,{"code":"2330"}]}
        self.assertEqual([p["code"] for p in extract(feed)["picks"]],["2330"])

    def test_reject_boolean_limit(self):
        with self.assertRaises(ValueError):
            extract({"data_date":"2026-10-16"},limit=True)

    def test_reject_invalid_feed(self):
        with self.assertRaises(ValueError):
            extract({"data_date":"2026-10-16","monster":{}})
        with self.assertRaises(ValueError):
            extract({"data_date":"2026-10-16"},limit=0)

    def test_snapshot_records_capture_time_not_last_checked_time(self):
        feed={"data_date":"2026-10-22","updated_at":"2026-10-22 20:22",
              "market":{"last_checked_at":"2026-10-23 23:09"},
              "attack":[{"code":"2330"}]}
        result=extract(feed)
        self.assertEqual(result["captured_at"],"2026-10-22 20:22")
        self.assertEqual(result["picks"][0]["as_of"],"2026-10-22")

    def test_missing_capture_time_remains_explicitly_missing(self):
        result=extract({"data_date":"2026-10-22","attack":[]})
        self.assertIsNone(result["captured_at"])

if __name__=="__main__":
    unittest.main()
