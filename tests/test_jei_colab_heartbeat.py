import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from tools.jei_colab_heartbeat import heartbeat_payload, write_heartbeat, start_heartbeat
from tools.jei_colab_watchdog import assess


class HeartbeatTests(unittest.TestCase):
    def test_emitted_heartbeat_readable_by_watchdog(self):
        now = dt.datetime(2026, 11, 13, 1, 0, tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "heartbeat.json"
            write_heartbeat(path, heartbeat_payload("session", "sha", now))
            result = assess(json.loads(path.read_text()), now=now)
            self.assertEqual(result["status"], "RECENT_HEARTBEAT")

    def test_stale_heartbeat_is_detected(self):
        old = dt.datetime(2026, 11, 13, 0, 0, tzinfo=dt.timezone.utc)
        now = old + dt.timedelta(minutes=60)
        self.assertEqual(assess(heartbeat_payload("session", "sha", old), now=now)["status"], "STALE")

    def test_thread_can_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            stop, thread = start_heartbeat(Path(tmp) / "heartbeat.json", interval_seconds=300)
            stop.set()
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())

    def test_reject_too_frequent_writes(self):
        with self.assertRaises(ValueError):
            start_heartbeat("unused", interval_seconds=1)


if __name__ == "__main__":
    unittest.main()
