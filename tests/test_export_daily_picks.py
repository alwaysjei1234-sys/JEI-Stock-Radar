import unittest
from scripts.export_daily_picks import extract

class DailyPickExportTests(unittest.TestCase):
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

    def test_reject_invalid_feed(self):
        with self.assertRaises(ValueError):
            extract({"data_date":"2026-10-16","monster":{}})
        with self.assertRaises(ValueError):
            extract({"data_date":"2026-10-16"},limit=0)

if __name__=="__main__":
    unittest.main()
