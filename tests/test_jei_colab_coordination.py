import datetime as dt
import json
import unittest
from pathlib import Path

from tools.jei_colab_coordination import merge_status, sanitized_status

NOW = dt.datetime(2026, 11, 18, 1, 12, tzinfo=dt.timezone.utc)


class ColabCoordinationTests(unittest.TestCase):
    def test_missing_drive_never_claims_alive_or_restarted(self):
        for data in (None, {}, {"status": "RECENT_HEARTBEAT"},
                     {"status": "STALE", "drive_access": "unavailable"},
                     {"status": "RECENT_HEARTBEAT", "drive_access": "unconfigured"}):
            with self.subTest(data=data):
                output = merge_status(data, now=NOW)
                self.assertEqual(output["colab_status"], "UNKNOWN")
                self.assertFalse(output["restart_possible"])
                self.assertEqual(output["fallback"], "github_actions")

    def test_only_authenticated_heartbeat_can_confirm_recent_or_stale(self):
        for state in ("RECENT_HEARTBEAT", "STALE"):
            output = merge_status({"status": state, "drive_access": "authenticated"}, now=NOW)
            self.assertEqual(output["colab_status"], state)
            self.assertEqual(output["evidence"], "authenticated_google_drive_heartbeat")
            self.assertNotIn("automatically_restart", output["requested_action"])
            self.assertFalse(output["restart_possible"])

    def test_new_timestamp_only_when_state_changes(self):
        prior = merge_status({"status": "STALE", "drive_access": "authenticated"}, now=NOW)
        later = NOW + dt.timedelta(hours=3)
        unchanged = merge_status({"status": "STALE", "drive_access": "authenticated"}, prior, later)
        self.assertEqual(unchanged, prior)
        changed = merge_status({"status": "RECENT_HEARTBEAT", "drive_access": "authenticated"}, prior, later)
        self.assertEqual(changed["status_changed_at_utc"], later.isoformat())

    def test_dangerous_untrusted_fields_are_never_published(self):
        secret = "NEVER-PUBLISH-THIS-TOKEN"
        out = merge_status({"status": "STALE", "drive_access": "authenticated",
                            "user_email": secret, "service_account": secret,
                            "file_id": secret, "session_id": secret}, now=NOW)
        self.assertNotIn(secret, json.dumps(out))
        self.assertNotIn("file_id", out)
        self.assertEqual(out["schema"], 1)

    def test_bad_or_future_previous_timestamp_is_not_reused(self):
        prior = merge_status({"status": "UNKNOWN", "drive_access": "unconfigured"}, now=NOW)
        for timestamp in ("wrong", (NOW + dt.timedelta(days=1)).isoformat(), None):
            out = merge_status({"status": "UNKNOWN", "drive_access": "unconfigured"},
                               {**prior, "status_changed_at_utc": timestamp}, now=NOW)
            self.assertEqual(out["status_changed_at_utc"], NOW.isoformat())

    def test_workflow_runs_fallback_then_writes_transition_not_hourly_commits(self):
        workflow = Path(".github/workflows/jei-colab-audit.yml").read_text(encoding="utf-8")
        self.assertIn("python -m tools.jei_shared_compute --provider github_actions", workflow)
        self.assertIn("python -m tools.jei_drive_heartbeat_ingest", workflow)
        self.assertIn("python -m tools.jei_colab_coordination", workflow)
        self.assertIn("git diff --quiet -- remote/colab_coordination.json", workflow)
        self.assertIn("paths-ignore:", workflow)
        self.assertIn("publish_coordination:", workflow)
        self.assertIn("github.event_name == 'schedule'", workflow)
        self.assertNotIn("git push --force", workflow)


if __name__ == "__main__":
    unittest.main()
