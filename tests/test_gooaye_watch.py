import importlib.util
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gooaye_watch", ROOT / "scripts" / "update_gooaye_watch.py")
watch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watch)


class GooayeWatchTests(unittest.TestCase):
    def setUp(self):
        self.rss = (ROOT / "tests/fixtures/gooaye_rss.xml").read_bytes()
        self.page = (ROOT / "tests/fixtures/gooaye_summary.html").read_bytes()

    def test_rss_keeps_episode_index_only(self):
        episodes = watch.parse_rss(self.rss)
        self.assertEqual([row["episode"] for row in episodes], ["EP708", "EP707"])
        self.assertEqual(episodes[0]["publishedAt"], "2026-10-25")
        self.assertNotIn("description", episodes[0])

    def test_summary_date_is_parsed_without_storing_summary_content(self):
        payload = watch.build_watch(self.rss, self.page, datetime(2026, 10, 25, tzinfo=timezone.utc))
        self.assertEqual(payload["summaryPage"]["lastUpdated"], "2026-06-29")
        self.assertFalse(payload["summaryPage"]["contentCopied"])
        self.assertTrue(payload["podcast"]["metadataOnly"])
        self.assertFalse(payload["podcast"]["descriptionsStored"])
        self.assertFalse(payload["podcast"]["transcriptsStored"])
        self.assertNotIn("完整節目描述不可保存", json.dumps(payload, ensure_ascii=False))

    def test_bad_or_empty_rss_is_rejected_instead_of_fabricating_titles(self):
        with self.assertRaises(ValueError):
            watch.parse_rss(b"<rss><channel><item><title>Untitled</title></item></channel></rss>")
        self.assertIsNone(watch.parse_summary_date("no date"))


if __name__ == "__main__":
    unittest.main()
