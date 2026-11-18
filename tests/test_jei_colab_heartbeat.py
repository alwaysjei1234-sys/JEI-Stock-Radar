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
            write_heartbeat(path, heartbeat_payload("session", "a" * 40, now))
            result = assess(json.loads(path.read_text()), now=now)
            self.assertEqual(result["status"], "RECENT_HEARTBEAT")

    def test_stale_heartbeat_is_detected(self):
        old = dt.datetime(2026, 11, 13, 0, 0, tzinfo=dt.timezone.utc)
        now = old + dt.timedelta(minutes=60)
        self.assertEqual(assess(heartbeat_payload("session", "a" * 40, old), now=now)["status"], "STALE")

    def test_thread_can_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            stop, thread = start_heartbeat(Path(tmp) / "heartbeat.json", interval_seconds=300)
            stop.set()
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())

    def test_reads_allowlisted_github_fallback_signal_without_credentials(self):
        from unittest.mock import patch
        from io import BytesIO
        from tools.jei_colab_heartbeat import read_github_coordination
        response = {"schema": 1, "colab_status": "STALE",
                    "fallback": "github_actions", "restart_possible": False,
                    "status_changed_at_utc": "2026-11-18T01:00:00+00:00",
                    "PRIVATE_TOKEN": "never-leak"}
        with patch("urllib.request.urlopen", return_value=BytesIO(json.dumps(response).encode())) as fetch:
            value = read_github_coordination()
        self.assertEqual(value["state"], "STALE")
        self.assertNotIn("PRIVATE_TOKEN", json.dumps(value))
        self.assertIn("raw.githubusercontent.com", fetch.call_args.args[0].full_url)

    def test_rejects_untrusted_restart_instruction(self):
        from unittest.mock import patch
        from io import BytesIO
        from tools.jei_colab_heartbeat import read_github_coordination
        for wrong in ({"schema": 1, "colab_status": "STALE",
                       "fallback": "github_actions", "restart_possible": True},
                      {"schema": 1, "colab_status": "RUNNING",
                       "fallback": "github_actions", "restart_possible": False}):
            with self.subTest(data=wrong), patch("urllib.request.urlopen",
                                                 return_value=BytesIO(json.dumps(wrong).encode())):
                with self.assertRaisesRegex(ValueError, "untrusted_github_coordination"):
                    read_github_coordination()

    def test_notebook_wires_bidirectional_status_only_while_kernel_is_alive(self):
        notebook = json.loads((Path("colab") / "JEI_Colab_Audit.ipynb").read_text(encoding="utf-8"))
        code = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])
        self.assertIn("coordination_reader=module.read_github_coordination", code)
        self.assertIn("colab_heartbeat.json", code)
        self.assertNotIn("force_restart_colab", code)

    def test_reject_too_frequent_writes(self):
        with self.assertRaises(ValueError):
            start_heartbeat("unused", interval_seconds=1)


if __name__ == "__main__":
    unittest.main()
