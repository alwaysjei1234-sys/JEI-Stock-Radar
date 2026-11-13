import datetime as dt
import unittest
from tools.jei_colab_watchdog import assess


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 11, 13, 1, 0, tzinfo=dt.timezone.utc)

    def test_no_report_is_unknown_not_stale(self):
        self.assertEqual(assess(None, now=self.now)["status"], "UNKNOWN")

    def test_recent_heartbeat_is_not_runtime_proof(self):
        result = assess({"provider": "google_colab", "heartbeat_at_utc": "2026-11-13T00:50:00Z"}, now=self.now)
        self.assertEqual(result["status"], "RECENT_HEARTBEAT")
        self.assertFalse(result["restart_possible"])

    def test_stalled_heartbeat(self):
        result = assess({"provider": "google_colab", "heartbeat_at_utc": "2026-11-13T00:00:00Z"}, now=self.now)
        self.assertEqual(result["status"], "STALE")
        self.assertEqual(result["fallback"], "github_actions")

    def test_github_run_cannot_masquerade_as_colab(self):
        self.assertEqual(assess({"provider": "github_actions", "heartbeat_at_utc": "2026-11-13T00:59:00Z"}, now=self.now)["status"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
