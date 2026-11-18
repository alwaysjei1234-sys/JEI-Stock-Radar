"""10 deterministic simulated GitHub -> Colab -> GitHub work handoffs.

All ten cycles invoke production modules, but Drive/GitHub I/O is mocked.
These tests do NOT establish that a live free Colab kernel has run or that
Drive service-account access has been configured. Test evidence must be
reported as simulation, never as ten real external Colab executions.
"""
import datetime as dt
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.jei_colab_coordination import merge_status
from tools.jei_colab_heartbeat import (
    audit_observed_picks, heartbeat_payload, read_github_coordination,
    write_heartbeat,
)
from tools.jei_drive_heartbeat_ingest import ingest


class TenReciprocalColabActionsRoundTrips(unittest.TestCase):
    def test_ten_distinct_daily_tasks_complete_both_directions(self):
        """10/10: Actions issues -> Colab evaluates -> authenticated Drive -> Actions reviews."""
        now = dt.datetime.now(dt.timezone.utc)
        days = []
        for shift in range(14):
            day = dt.date(2026, 11, 2) + dt.timedelta(days=shift)
            if day.weekday() < 5:
                days.append(day.isoformat())
        self.assertEqual(len(days), 10)
        successes = []

        for number, day in enumerate(days, start=1):
            with self.subTest(round=number, official_day=day), tempfile.TemporaryDirectory() as folder:
                picks = {
                    "latest_official_day": day,
                    "groups": {
                        "attack": {"3": {
                            "completed": 40, "win_rate_pct": 25.0,
                            "avg_estimated_net_pct": -2.5}},
                        "next": {"7": {
                            "completed": 31, "win_rate_pct": 55.0,
                            "avg_estimated_net_pct": 1.8}},
                    },
                }
                # GitHub -> Colab: public request is limited to official-date
                # observed-data validation; no shell, remote code or credentials.
                offered = merge_status(None, now=now, picks=picks)
                task = offered["colab_task"]
                self.assertEqual(task["task_id"], "observed-" + day)
                with patch("urllib.request.urlopen", return_value=io.BytesIO(
                        json.dumps(offered).encode("utf-8"))):
                    signal = read_github_coordination()
                self.assertEqual(signal["task"], task)
                self.assertEqual(signal["state"], "UNKNOWN")

                # Colab: execute real bounded observed comparison function.
                work = audit_observed_picks(
                    signal["task"],
                    fetcher=lambda: json.dumps(picks).encode("utf-8"))
                self.assertEqual(work["status"], "completed")
                self.assertTrue(work["observed_only"])
                self.assertEqual(work["eligible_aggregates"], 2)
                self.assertEqual(work["underperforming_aggregates"], 1)

                # Colab -> Drive: actual writer and reader run against a
                # temporary private file, not the user's Google Drive.
                heartbeat = heartbeat_payload(
                    "test-session-" + str(number), "a" * 40, now=now)
                heartbeat["colab_task_result"] = work
                heartbeat["actions_request"] = "review_pick_quality"
                heartbeat["private_value"] = "NOT_FOR_PUBLIC_REPOSITORY"
                private_path = Path(folder) / "colab_heartbeat.json"
                write_heartbeat(private_path, heartbeat)
                actual_disk = json.loads(private_path.read_text(encoding="utf-8"))

                # Actions: service-account download is mocked, but the real
                # Drive ingestion, Colab watchdog and coordinator are executed.
                with patch("tools.jei_drive_heartbeat_ingest.download_heartbeat",
                           return_value=actual_disk):
                    ingested = ingest(
                        "mock-drive-file", "mock-service-account",
                        Path(folder) / "watchdog.json")
                self.assertEqual(ingested["drive_access"], "authenticated")
                self.assertEqual(ingested["status"], "RECENT_HEARTBEAT")
                self.assertEqual(ingested["colab_request"], "review_pick_quality")
                self.assertNotIn("private_value", json.dumps(ingested))

                reviewed = merge_status(
                    ingested, previous=offered, now=now, picks=picks)
                self.assertEqual(reviewed["colab_task_ack"]["task_id"], task["task_id"])
                self.assertEqual(reviewed["colab_task_ack"]["status"],
                                 "reported_not_independently_attested")
                self.assertEqual(reviewed["colab_requested_audit"],
                                 "review_pick_quality")
                self.assertNotIn("NOT_FOR_PUBLIC_REPOSITORY", json.dumps(reviewed))

                # A repeated heartbeat cannot create a new coordination
                # transition or a duplicate request for the same date.
                same = merge_status(
                    ingested, previous=reviewed,
                    now=now + dt.timedelta(minutes=5), picks=picks)
                self.assertEqual(same, reviewed)
                successes.append(day)
        self.assertEqual(successes, days)
        self.assertEqual(len(successes), 10)

    def test_disconnected_colab_never_fakes_roundtrip(self):
        now = dt.datetime.now(dt.timezone.utc)
        picks = {"latest_official_day": "2026-11-17", "groups": {"attack": {}}}
        for evidence in (None, {"status": "STALE", "drive_access": "authenticated"},
                         {"status": "RECENT_HEARTBEAT", "drive_access": "unconfigured"}):
            with self.subTest(evidence=evidence):
                result = merge_status(evidence, now=now, picks=picks)
                self.assertIsNone(result["colab_task_ack"])
                self.assertIsNone(result["colab_requested_audit"])
                self.assertFalse(result["restart_possible"])

    def test_mismatched_snapshot_never_acknowledges(self):
        now = dt.datetime.now(dt.timezone.utc)
        task = {"kind": "audit_observed_picks",
                "task_id": "observed-2026-11-17",
                "official_day": "2026-11-17"}
        wrong = {"latest_official_day": "2026-11-16", "groups": {}}
        with self.assertRaisesRegex(ValueError, "official_date_changed"):
            audit_observed_picks(
                task, fetcher=lambda: json.dumps(wrong).encode("utf-8"))

    def test_no_execution_instructions_from_public_state(self):
        public = {"schema": 1, "colab_status": "UNKNOWN",
                  "fallback": "github_actions", "restart_possible": False,
                  "colab_task": {"kind": "execute_shell_script",
                                 "task_id": "observed-2026-11-17",
                                 "official_day": "2026-11-17",
                                 "command": "echo unsafe"}}
        with patch("urllib.request.urlopen",
                   return_value=io.BytesIO(json.dumps(public).encode())):
            signal = read_github_coordination()
        self.assertNotIn("task", signal)


if __name__ == "__main__":
    unittest.main()
