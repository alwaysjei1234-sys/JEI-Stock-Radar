import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools.jei_batch_checkpoint import save_checkpoint, load_checkpoint
from tools.jei_drive_heartbeat_ingest import ingest


class CheckpointTests(unittest.TestCase):
    def test_resume_exact_source_and_parameters(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoint.json"
            save_checkpoint(path, "hash", "attack", {"period": 3}, {"batch-1": {"count": 5}})
            self.assertEqual(load_checkpoint(path, "hash", "attack", {"period": 3})["batch-1"]["count"], 5)
            with self.assertRaises(ValueError):
                load_checkpoint(path, "different", "attack", {"period": 3})
            with self.assertRaises(ValueError):
                load_checkpoint(path, "hash", "attack", {"period": 7})

    def test_rejects_changed_payload_or_metadata_with_unchanged_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoint.json"
            original = save_checkpoint(path, "hash", "attack", {"period": 3}, {"batch": {"count": 5}})
            for changes in (
                {"completed_batches": {"batch": {"count": 99}}},
                {"strategy": "monster"},
                {"parameters": {"period": 7}},
                {"schema": 99},
            ):
                with self.subTest(changes=changes):
                    path.write_text(json.dumps({**original, **changes}))
                    with self.assertRaises(ValueError):
                        load_checkpoint(path, "hash", "attack", {"period": 3})

    def test_missing_drive_credentials_never_fakes_colab(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            for file_id, credentials, missing in (
                (None, None, ["file_id", "service_account"]),
                ("file", None, ["service_account"]),
                (None, "credentials", ["file_id"]),
            ):
                with self.subTest(missing=missing), patch(
                        "tools.jei_drive_heartbeat_ingest.download_heartbeat") as download:
                    result = ingest(file_id, credentials, path)
                    download.assert_not_called()
                    self.assertEqual(result["status"], "UNKNOWN")
                    self.assertEqual(result["drive_access"], "unconfigured")
                    self.assertEqual(result["reason"], "drive_configuration_missing")
                    self.assertEqual(result["missing_configuration"], missing)
                    self.assertEqual(result["fallback"], "github_actions")
                    self.assertEqual(json.loads(path.read_bytes()), result)

    def test_drive_read_failure_excludes_exception_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            with patch("tools.jei_drive_heartbeat_ingest.download_heartbeat",
                       side_effect=ValueError("private configuration")):
                result = ingest("file", "credentials", path)
            self.assertEqual(result["status"], "UNKNOWN")
            self.assertEqual(result["drive_access"], "unavailable")
            self.assertEqual(result["reason"], "drive_read_failed")
            self.assertEqual(result["error_type"], "ValueError")
            self.assertNotIn("private configuration", path.read_text())

    def test_valid_drive_heartbeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            from datetime import datetime, timezone
            heartbeat = {"provider": "google_colab",
                         "heartbeat_at_utc": datetime.now(timezone.utc).isoformat()}
            with patch("tools.jei_drive_heartbeat_ingest.download_heartbeat", return_value=heartbeat):
                result = ingest("file", "credentials", Path(tmp) / "status.json")
            self.assertEqual(result["status"], "RECENT_HEARTBEAT")


if __name__ == "__main__":
    unittest.main()
