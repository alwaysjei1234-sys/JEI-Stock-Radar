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

    def test_missing_drive_credentials_never_fakes_colab(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = ingest(None, None, Path(tmp) / "status.json")
            self.assertEqual(result["status"], "UNKNOWN")
            self.assertEqual(result["fallback"], "github_actions")

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
