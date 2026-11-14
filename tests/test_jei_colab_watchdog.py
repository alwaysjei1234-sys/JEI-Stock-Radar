import datetime as dt
import unittest
from tools.jei_colab_heartbeat import heartbeat_payload
from tools.jei_colab_watchdog import assess


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 11, 13, 1, 0, tzinfo=dt.timezone.utc)

    def test_no_report_is_unknown_not_stale(self):
        self.assertEqual(assess(None, now=self.now)["status"], "UNKNOWN")

    def test_incomplete_or_unsupported_identity_is_unknown(self):
        valid = heartbeat_payload("session", "a" * 40, self.now)
        for changes in (
            {"schema": None}, {"schema": True}, {"schema": 2},
            {"session_id": " "}, {"source_commit": "unknown"},
            {"source_commit": "a" * 39}, {"source_commit": "z" * 40},
        ):
            with self.subTest(changes=changes):
                result = assess({**valid, **changes}, now=self.now)
                self.assertEqual(result["status"], "UNKNOWN")
                self.assertEqual(result["reason"], "invalid_heartbeat_identity")

    def test_recent_heartbeat_is_not_runtime_proof(self):
        result = assess(heartbeat_payload("session", "a" * 40, dt.datetime.fromisoformat("2026-11-13T00:50:00+00:00")), now=self.now)
        self.assertEqual(result["status"], "RECENT_HEARTBEAT")
        self.assertFalse(result["restart_possible"])

    def test_stalled_heartbeat(self):
        result = assess(heartbeat_payload("session", "a" * 40, dt.datetime.fromisoformat("2026-11-13T00:00:00+00:00")), now=self.now)
        self.assertEqual(result["status"], "STALE")
        self.assertEqual(result["fallback"], "github_actions")

    def test_github_run_cannot_masquerade_as_colab(self):
        self.assertEqual(assess({"provider": "github_actions", "heartbeat_at_utc": "2026-11-13T00:59:00Z"}, now=self.now)["status"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
