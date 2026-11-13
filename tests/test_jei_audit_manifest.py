import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.jei_audit_manifest import OUTPUTS, build_manifest


class AuditManifestTests(unittest.TestCase):
    def test_hashes_present_outputs_and_marks_missing_files(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            data = b'{"status":"UNKNOWN"}\n'
            (directory / "colab_watchdog.json").write_bytes(data)
            (directory / "unrelated.json").write_text("{}")
            result = build_manifest(directory, {
                "GITHUB_EVENT_NAME": "schedule", "GITHUB_RUN_ID": "123",
                "GITHUB_RUN_ATTEMPT": "2", "GITHUB_SHA": "a" * 40,
            })
        self.assertEqual(result["event"], "schedule")
        self.assertEqual(result["run_attempt"], "2")
        self.assertEqual(result["source_commit"], "a" * 40)
        self.assertEqual(result["files"], {
            "colab_watchdog.json": {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        })
        self.assertEqual(result["missing"], sorted(set(OUTPUTS) - {"colab_watchdog.json"}))
