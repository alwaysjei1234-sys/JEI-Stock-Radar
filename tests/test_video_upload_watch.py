import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from scripts import update_video_upload_watch as watch


class VideoUploadWatchTests(TestCase):
    def setUp(self):
        self.channel = {
            "id": "yt-01", "name": "測試頻道", "level": "中階", "focus": "美股與產業",
            "channelId": "UC1234567890123456789012", "rssEnabled": True,
            "rssUrl": "https://www.youtube.com/feeds/videos.xml?channel_id=UC1234567890123456789012",
        }

    def test_parses_only_official_rss_titles_dates_and_watch_links(self):
        fixture = Path(__file__).parent / "fixtures" / "youtube_channel_feed.xml"
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return fixture.read_bytes()
        with patch.object(watch.urllib.request, "urlopen", return_value=Response()):
            channel, videos = watch._fetch_channel(self.channel)
        self.assertEqual(channel["name"], "測試頻道")
        self.assertEqual(len(videos), 2)
        self.assertEqual(videos[0]["title"], "美股半導體與台股研究方法")
        self.assertEqual(videos[0]["url"], "https://www.youtube.com/watch?v=AbCdEf12345")
        self.assertNotIn("transcript", str(videos).lower())

    def test_rejects_non_youtube_feed_url(self):
        bad = {**self.channel, "rssUrl": "https://example.com/feed.xml"}
        with self.assertRaisesRegex(ValueError, "official YouTube feed"):
            watch._fetch_channel(bad)

    def test_partial_or_total_outage_reuses_previous_rows_and_reports_failures(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            sources, output = root / "sources.json", root / "watch.json"
            channel2 = {**self.channel, "id": "yt-02", "name": "故障頻道", "channelId": "UCabcdefghijabcdefghij12",
                        "rssUrl": "https://www.youtube.com/feeds/videos.xml?channel_id=UCabcdefghijabcdefghij12"}
            sources.write_text(json.dumps({"channels": [self.channel, channel2]}), encoding="utf-8")
            output.write_text(json.dumps({"videos": [{"channelId": channel2["id"], "url": "https://www.youtube.com/watch?v=old", "publishedAt": "2026-10-23"}]}), encoding="utf-8")
            rows = [{"channelId": self.channel["id"], "url": "https://www.youtube.com/watch?v=new", "publishedAt": "2026-10-24"}]
            with patch.object(watch, "SOURCES", sources), patch.object(watch, "OUTPUT", output), patch.object(watch, "_fetch_channel", side_effect=[(self.channel, rows), RuntimeError("offline")]):
                data = watch.refresh()
            self.assertEqual(data["successfulSourceCount"], 1)
            self.assertEqual({item["url"] for item in data["videos"]}, {"https://www.youtube.com/watch?v=new", "https://www.youtube.com/watch?v=old"})
            with patch.object(watch, "SOURCES", sources), patch.object(watch, "OUTPUT", output), patch.object(watch, "_fetch_channel", side_effect=RuntimeError("offline")):
                all_failed = watch.refresh()
            self.assertEqual(all_failed["successfulSourceCount"], 0)
            self.assertEqual(len(all_failed["failedSources"]), 2)
            self.assertEqual({item["url"] for item in all_failed["videos"]}, {"https://www.youtube.com/watch?v=old"})

