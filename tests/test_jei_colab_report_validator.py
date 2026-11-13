import datetime as dt
import unittest
import hashlib
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
            "source_commit": "abcdef", "status": "completed",
            "outputs": {"diagnostics": "jei_diagnostics.json"},
            "output_sha256": {"diagnostics": hashlib.sha256(b"test").hexdigest()}}

    def test_recent_completed_report(self):
        self.assertTrue(validate(self.report, now=self.now)["verified"])

    def test_output_file_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "jei_diagnostics.json"
            file.write_bytes(b"test")
            self.assertTrue(validate(self.report, now=self.now, output_dir=tmp)["verified"])
            file.write_bytes(b"tampered")
            self.assertIn("output_hash_mismatch_diagnostics",
                          validate(self.report, now=self.now, output_dir=tmp)["issues"])

    def test_commit_mismatch_rejected(self):
        result = validate(self.report, now=self.now, expected_commit="other")
        self.assertIn("source_commit_mismatch", result["issues"])

    def test_path_traversal_rejected(self):
        self.report["outputs"]["diagnostics"] = "../secret.txt"
        self.assertFalse(validate(self.report, now=self.now)["verified"])

    def test_stale_report_rejected(self):
        self.assertFalse(validate(self.report, now=self.now + dt.timedelta(hours=4))["verified"])

    def test_missing_outputs_rejected(self):
        self.report["outputs"] = {}
        self.assertFalse(validate(self.report, now=self.now)["verified"])

    def test_claiming_github_actions_as_colab_rejected(self):
        self.report["provider"] = "github_actions"
        self.assertFalse(validate(self.report, now=self.now)["verified"])

    def test_future_report_rejected(self):
        self.assertFalse(validate(self.report, now=self.now - dt.timedelta(hours=2))["verified"])


if __name__ == "__main__":
    unittest.main()
