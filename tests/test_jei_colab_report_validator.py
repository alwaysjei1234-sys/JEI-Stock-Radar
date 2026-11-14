import datetime as dt
import unittest
import hashlib
import json
import tempfile
from pathlib import Path
from tools.jei_colab_report_validator import validate
from tools.jei_shared_compute import compute


class ColabReportTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 11, 13, 1, tzinfo=dt.timezone.utc)
        self.report = {
            "provider": "google_colab", "run_id": "run-123",
            "started_at_utc": "2026-11-13T00:30:00+00:00",
            "finished_at_utc": "2026-11-13T00:40:00+00:00",
            "source_commit": "abcdef0123456789abcdef0123456789abcdef01", "status": "completed",
            "outputs": {"diagnostics": "jei_diagnostics.json"},
            "output_sha256": {"diagnostics": hashlib.sha256(b"test").hexdigest()}}

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.output_dir = Path(directory.name)
        self.output_file = self.output_dir / "jei_diagnostics.json"
        diagnostic = json.dumps({k: self.report[k] for k in ("source_commit", "started_at_utc")}).encode()
        self.output_file.write_bytes(diagnostic)
        self.report["output_sha256"]["diagnostics"] = hashlib.sha256(diagnostic).hexdigest()
        self.source = self.output_dir / "pick_validation.json"
        self.source.write_text(json.dumps({"groups": {"attack": {"3": {
            "completed": 31, "win_rate_pct": 55, "avg_estimated_net_pct": 1.2
        }}}}))

    def validate(self, **kwargs):
        options = {"now": self.now, "expected_commit": self.report["source_commit"],
                   "output_dir": self.output_dir, "source_path": self.source}
        options.update(kwargs)
        return validate(self.report, **options)

    def attach_compute(self, **override):
        observed = {
            "compute_provider": "google_colab",
            "source_commit": self.report["source_commit"],
            "source_sha256": hashlib.sha256(self.source.read_bytes()).hexdigest(),
            **compute(json.loads(self.source.read_bytes())),
            **override,
        }
        raw = json.dumps(observed).encode()
        (self.output_dir / "observed.json").write_bytes(raw)
        self.report["outputs"]["observed_compute"] = "observed.json"
        self.report["output_sha256"]["observed_compute"] = hashlib.sha256(raw).hexdigest()

    def test_observed_compute_must_match_colab_metadata(self):
        for override in (
            {"compute_provider": "github_actions"}, {"source_commit": "b" * 40},
            {"source_sha256": "invalid"}, {"observed_rows": []},
        ):
            with self.subTest(override=override):
                self.attach_compute(**override)
                self.assertFalse(self.validate()["verified"])
        self.attach_compute()
        self.assertTrue(self.validate()["verified"])

    def test_source_and_recomputed_result_must_match(self):
        self.attach_compute(source_sha256="b" * 64)
        self.assertIn("observed_source_hash_mismatch", self.validate()["issues"])
        self.attach_compute(eligible_rows=99, independent_oos_verified=True)
        self.assertIn("observed_replay_mismatch", self.validate()["issues"])
        self.attach_compute()
        self.assertFalse(self.validate(source_path=None)["verified"])

    def test_diagnostics_only_cannot_verify_completed_compute(self):
        self.assertFalse(self.validate()["verified"])

    def test_recent_completed_report(self):
        self.attach_compute()
        self.assertTrue(self.validate()["verified"])

    def test_report_without_reference_or_bytes_is_unverified(self):
        result = validate(self.report, now=self.now)
        self.assertFalse(result["verified"])
        self.assertIn("missing_expected_commit", result["issues"])
        self.assertIn("missing_output_directory", result["issues"])

    def test_output_file_integrity(self):
        self.output_file.write_bytes(b"tampered")
        self.assertIn("output_hash_mismatch_diagnostics", self.validate()["issues"])
        self.output_file.unlink()
        self.assertIn("missing_output_file_diagnostics", self.validate()["issues"])

    def test_diagnostics_must_belong_to_the_same_run(self):
        self.attach_compute()
        for content, issue in (
            (b"not JSON", "invalid_diagnostics"),
            (b"[]", "invalid_diagnostics"),
            (json.dumps({"source_commit": "b" * 40, "started_at_utc": self.report["started_at_utc"]}).encode(),
             "diagnostics_commit_mismatch"),
            (json.dumps({"source_commit": self.report["source_commit"], "started_at_utc": "2026-11-13T00:10:00Z"}).encode(),
             "diagnostics_start_mismatch"),
        ):
            with self.subTest(issue=issue):
                self.output_file.write_bytes(content)
                self.report["output_sha256"]["diagnostics"] = hashlib.sha256(content).hexdigest()
                self.assertIn(issue, self.validate()["issues"])

    def test_commit_mismatch_rejected(self):
        result = self.validate(expected_commit="0" * 40)
        self.assertIn("source_commit_mismatch", result["issues"])

    def test_short_commit_rejected_even_when_matching(self):
        self.report["source_commit"] = "abcdef"
        self.assertIn("invalid_source_commit", self.validate()["issues"])

    def test_path_traversal_rejected(self):
        self.attach_compute()
        self.report["outputs"]["diagnostics"] = "../secret.txt"
        self.assertFalse(self.validate()["verified"])

    def test_stale_report_rejected(self):
        self.assertFalse(self.validate(now=self.now + dt.timedelta(hours=4))["verified"])

    def test_missing_outputs_rejected(self):
        self.report["outputs"] = {}
        self.assertFalse(self.validate()["verified"])

    def test_claiming_github_actions_as_colab_rejected(self):
        self.report["provider"] = "github_actions"
        self.assertFalse(self.validate()["verified"])

    def test_future_report_rejected(self):
        self.assertFalse(self.validate(now=self.now - dt.timedelta(hours=2))["verified"])


if __name__ == "__main__":
    unittest.main()
