import datetime as dt
import unittest
import hashlib
import json
import tempfile
from pathlib import Path
from tools.jei_colab_report_validator import validate


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
        self.output_file.write_bytes(b"test")

    def validate(self, **kwargs):
        options = {"now": self.now, "expected_commit": self.report["source_commit"],
                   "output_dir": self.output_dir}
        options.update(kwargs)
        return validate(self.report, **options)

    def attach_compute(self, **override):
        observed = {
            "compute_provider": "google_colab",
            "source_commit": self.report["source_commit"],
            "source_sha256": "a" * 64,
            "observed_rows": [{"observed_count": 3}],
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
