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

    def test_github_issues_one_per_official_day_safe_task(self):
        from tools.jei_colab_coordination import task_from_picks
        picks = {"latest_official_day": "2026-11-17", "groups": {"attack": {}}}
        task = task_from_picks(picks)
        self.assertEqual(task, {"kind": "audit_observed_picks",
                                "task_id": "observed-2026-11-17",
                                "official_day": "2026-11-17"})
        for invalid in ({"latest_official_day": "bad", "groups": {}},
                        {"latest_official_day": "2026-02-30", "groups": {}},
                        {"latest_official_day": "2026-11-17", "groups": "bad"},
                        None):
            self.assertIsNone(task_from_picks(invalid))

    def test_colab_ack_requires_authenticated_recent_matching_completion(self):
        task_data = {"latest_official_day": "2026-11-17", "groups": {"attack": {}}}
        watch = {"status": "RECENT_HEARTBEAT", "drive_access": "authenticated",
                 "colab_task_result": {"task_id": "observed-2026-11-17",
                                       "status": "completed", "observed_only": True},
                 "colab_request": "review_pick_quality"}
        fresh = merge_status(watch, now=NOW, picks=task_data)
        self.assertEqual(fresh["colab_task_ack"]["status"],
                         "reported_not_independently_attested")
        self.assertEqual(fresh["colab_requested_audit"], "review_pick_quality")
        for change in ({"drive_access": "unconfigured"}, {"status": "STALE"},
                       {"colab_task_result": {"task_id": "observed-2026-11-16",
                                               "status": "completed", "observed_only": True}}):
            with self.subTest(change=change):
                result = merge_status({**watch, **change}, now=NOW, picks=task_data)
                self.assertIsNone(result["colab_task_ack"])
                if change.get("status") == "STALE" or change.get("drive_access") == "unconfigured":
                    self.assertIsNone(result["colab_requested_audit"])

    def test_drive_ingest_allowlists_requests_and_task_result(self):
        from unittest.mock import patch
        from tempfile import TemporaryDirectory
        from tools.jei_colab_heartbeat import heartbeat_payload
        from tools.jei_drive_heartbeat_ingest import ingest
        payload = heartbeat_payload("session", "a" * 40)
        payload.update(actions_request="review_pick_quality",
                       colab_task_result={"task_id": "observed-2026-11-17",
                                          "status": "completed", "observed_only": True,
                                          "secret": "DO_NOT_EXPOSE"})
        with TemporaryDirectory() as folder, patch(
                "tools.jei_drive_heartbeat_ingest.download_heartbeat",
                return_value=payload):
            report = ingest("fixture-id", "fixture-key", f"{folder}/result.json")
        self.assertEqual(report["colab_request"], "review_pick_quality")
        self.assertEqual(report["colab_task_result"]["task_id"], "observed-2026-11-17")
        self.assertNotIn("DO_NOT_EXPOSE", json.dumps(report))

    def test_colab_work_request_runs_extra_read_only_checks(self):
        workflow = Path(".github/workflows/jei-colab-audit.yml").read_text(encoding="utf-8")
        self.assertIn('status.get("colab_request") == "review_pick_quality"', workflow)
        self.assertIn("python -m unittest discover -s tests -p 'test_pick*.py'", workflow)
        self.assertIn("authenticated", workflow)
        self.assertNotIn("github.event_name == 'pull_request' && contents: write", workflow)

    def test_colab_work_request_is_published_after_main_push_not_only_schedule(self):
        # Regression: the audit used to compute a fresh task on GitHub push
        # but published it only on a future scheduled run. Until that run,
        # the public coordination file contained no task for live Colab.
        workflow = Path(".github/workflows/jei-colab-audit.yml").read_text(encoding="utf-8")
        publisher = workflow.split("\n  publish_coordination:\n", 1)[1]
        self.assertIn("needs.audit.result == 'success'", publisher)
        self.assertIn("github.event_name == 'schedule'", publisher)
        self.assertIn("github.event_name == 'push'", publisher)
        self.assertIn("github.ref == 'refs/heads/main'", publisher)
        self.assertIn("git diff --quiet -- remote/colab_coordination.json", publisher)
        self.assertIn("remote/colab_coordination.json", workflow.split("paths-ignore:", 1)[1])
        self.assertNotIn("github.event_name == 'pull_request'", publisher)

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

    def test_primary_compute_and_checkpoint_precede_optional_drive_access(self):
        workflow = Path(".github/workflows/jei-colab-audit.yml").read_text(encoding="utf-8")
        primary = workflow.split("\n  optional_colab_review:\n", 1)[0]
        self.assertLess(primary.index("Execute portable observed-performance computation"),
                        primary.index("Read Colab heartbeat from authorized Drive"))
        self.assertLess(primary.index("Persist checkpoint for future runs"),
                        primary.index("Read Colab heartbeat from authorized Drive"))
        self.assertNotIn("python -m unittest discover -s tests -p 'test_pick*.py'", primary)
        drive = primary.split("Read Colab heartbeat from authorized Drive", 1)[1].split("      - name:", 1)[0]
        self.assertIn("continue-on-error: true", drive)

    def test_optional_review_cannot_block_publication_and_is_main_only(self):
        workflow = Path(".github/workflows/jei-colab-audit.yml").read_text(encoding="utf-8")
        primary, rest = workflow.split("\n  optional_colab_review:\n", 1)
        optional, publisher = rest.split("\n  publish_coordination:\n", 1)
        self.assertIn("needs: audit", optional)
        self.assertIn("needs.audit.outputs.colab_review_authorized == 'true'", optional)
        self.assertIn("needs: audit", publisher)
        self.assertNotIn("optional_colab_review", publisher)
        self.assertNotIn("secrets.", optional)
        auth = primary.split("Authorize optional Colab review (main only)", 1)[1].split("      - name:", 1)[0]
        self.assertIn("github.ref == 'refs/heads/main'", auth)
        self.assertIn("github.event_name != 'pull_request'", auth)
        self.assertIn("authorized=false", auth)
        self.assertIn("continue-on-error: true", auth)
        self.assertIn("github.event_name == 'workflow_dispatch'", publisher)


if __name__ == "__main__":
    unittest.main()
