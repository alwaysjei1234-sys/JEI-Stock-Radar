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

    def test_failed_official_day_handoff_retries_after_cooldown(self):
        from tools.jei_colab_heartbeat import (
            allow_task_attempt, TASK_RETRY_COOLDOWN_SECONDS,
        )
        attempts = {}
        task = "observed-2026-11-18"
        self.assertTrue(allow_task_attempt(attempts, task, now=100))
        self.assertTrue(allow_task_attempt(attempts, task, now=400))
        self.assertTrue(allow_task_attempt(attempts, task, now=700))
        self.assertFalse(allow_task_attempt(attempts, task, now=1000))
        # A failed public-data read used to permanently block this day's task,
        # even after GitHub's delayed official close arrived hours later.
        self.assertFalse(allow_task_attempt(
            attempts, task, now=700 + TASK_RETRY_COOLDOWN_SECONDS - 1))
        self.assertTrue(allow_task_attempt(
            attempts, task, now=700 + TASK_RETRY_COOLDOWN_SECONDS))
        self.assertEqual(attempts[task][0], 1)

    def test_task_retry_state_is_bounded_and_resets_for_new_day(self):
        from tools.jei_colab_heartbeat import allow_task_attempt
        attempts = {}
        for i in range(3):
            self.assertTrue(allow_task_attempt(
                attempts, "observed-2026-11-18", now=100 + 300 * i))
        self.assertFalse(allow_task_attempt(attempts, "observed-2026-11-18", now=999))
        self.assertTrue(allow_task_attempt(
            attempts, "observed-2026-11-19", now=1000))
        self.assertEqual(list(attempts), ["observed-2026-11-19"])
        # Defensive reset if monotonic clock state is invalidated.
        self.assertTrue(allow_task_attempt(
            attempts, "observed-2026-11-19", now=0))
        self.assertEqual(attempts["observed-2026-11-19"][0], 1)

    def test_drive_writes_keep_stable_file_identity(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "colab_heartbeat.json"
            write_heartbeat(path, heartbeat_payload("one", "a" * 40),
                            preserve_drive_id=True)
            initial_inode = os.stat(path).st_ino
            write_heartbeat(path, heartbeat_payload("two", "a" * 40),
                            preserve_drive_id=True)
            self.assertEqual(os.stat(path).st_ino, initial_inode)
            self.assertEqual(json.loads(path.read_text())["session_id"], "two")
            self.assertFalse(path.with_name(path.name + ".tmp").exists())

    def test_initial_heartbeat_written_before_slow_network_coordination(self):
        import threading
        entered = threading.Event()
        release = threading.Event()
        def blocked_reader():
            entered.set()
            release.wait(timeout=2)
            return {"state": "UNKNOWN"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "heartbeat.json"
            try:
                stop, thread = start_heartbeat(
                    path, source_commit="a" * 40, interval_seconds=30,
                    coordination_reader=blocked_reader)
                self.assertTrue(path.exists())
                self.assertTrue(entered.wait(2))
                payload = json.loads(path.read_text())
                self.assertEqual(payload["provider"], "google_colab")
                self.assertEqual(payload["source_commit"], "a" * 40)
            finally:
                release.set()
                stop.set()
                thread.join(timeout=3)

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

    def test_accepts_only_bounded_verified_observation_task(self):
        from unittest.mock import patch
        from io import BytesIO
        from tools.jei_colab_heartbeat import read_github_coordination
        reply = {"schema": 1, "colab_status": "UNKNOWN",
                 "fallback": "github_actions", "restart_possible": False,
                 "colab_task": {"kind": "audit_observed_picks",
                                "task_id": "observed-2026-11-17",
                                "official_day": "2026-11-17"}}
        with patch("urllib.request.urlopen", return_value=BytesIO(json.dumps(reply).encode())):
            result = read_github_coordination()
        self.assertEqual(result["task"]["task_id"], "observed-2026-11-17")
        reply["colab_task"]["kind"] = "execute_shell_script"
        with patch("urllib.request.urlopen", return_value=BytesIO(json.dumps(reply).encode())):
            self.assertNotIn("task", read_github_coordination())

    def test_actual_observed_recheck_and_request_from_colab(self):
        from tools.jei_colab_heartbeat import audit_observed_picks
        task = {"kind": "audit_observed_picks", "task_id": "observed-2026-11-17",
                "official_day": "2026-11-17"}
        payload = {"latest_official_day": "2026-11-17",
                   "groups": {"attack": {"3": {"completed": 40, "win_rate_pct": 30,
                                                "avg_estimated_net_pct": -3.5},
                                          "7": {"completed": 10, "win_rate_pct": 90,
                                                "avg_estimated_net_pct": 4}},
                              "next": {"3": {"completed": 31, "win_rate_pct": 55,
                                              "avg_estimated_net_pct": 2.5}}}}
        result = audit_observed_picks(task, fetcher=lambda: json.dumps(payload).encode())
        self.assertEqual(result["eligible_aggregates"], 2)
        self.assertEqual(result["underperforming_aggregates"], 1)
        self.assertTrue(result["observed_only"])
        payload["latest_official_day"] = "2026-11-16"
        with self.assertRaisesRegex(ValueError, "official_date_changed"):
            audit_observed_picks(task, fetcher=lambda: json.dumps(payload).encode())

    def test_heartbeat_executes_task_once_and_returns_bounded_request(self):
        import threading
        task = {"kind": "audit_observed_picks", "task_id": "observed-2026-11-17",
                "official_day": "2026-11-17"}
        called = threading.Event()
        run_count = []
        def runner(request):
            run_count.append(request["task_id"])
            called.set()
            return {"task_id": request["task_id"], "status": "completed",
                    "observed_only": True, "eligible_aggregates": 1,
                    "underperforming_aggregates": 1, "secret": "NOT_WRITTEN"}
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "heartbeat.json"
            stop, thread = start_heartbeat(
                file, source_commit="a" * 40, interval_seconds=30,
                coordination_reader=lambda: {"state": "UNKNOWN", "task": task},
                task_runner=runner)
            try:
                self.assertTrue(called.wait(3))
                # Callback runs before the atomic heartbeat write; avoid a
                # scheduler-dependent race in the test itself.
                import time
                for _ in range(100):
                    if file.exists():
                        report = json.loads(file.read_text(encoding="utf-8"))
                        if "colab_task_result" in report:
                            break
                    time.sleep(0.01)
                self.assertIn("colab_task_result", report)
                self.assertEqual(report["actions_request"], "review_pick_quality")
                self.assertEqual(report["colab_task_result"]["task_id"], task["task_id"])
                self.assertNotIn("NOT_WRITTEN", json.dumps(report))
                self.assertEqual(len(run_count), 1)
            finally:
                stop.set()
                thread.join(timeout=3)

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
        self.assertIn("task_runner=module.audit_observed_picks", code)
        self.assertIn("colab_heartbeat.json", code)
        self.assertNotIn("force_restart_colab", code)

    def test_reject_too_frequent_writes(self):
        with self.assertRaises(ValueError):
            start_heartbeat("unused", interval_seconds=1)


if __name__ == "__main__":
    unittest.main()
