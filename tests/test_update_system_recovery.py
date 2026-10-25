import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.update_system import load_previous_risk


class PreviousRiskRecoveryTests(unittest.TestCase):
    def test_valid_current_feed_is_used_without_git(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "system.json"
            path.write_text(json.dumps({"risk": {"score": 87, "level": "red"}}), encoding="utf-8")
            with patch("scripts.update_system.subprocess.run") as run:
                risk, warning = load_previous_risk(path)
            run.assert_not_called()
            self.assertEqual(risk["score"], 87)
            self.assertIsNone(warning)

    def test_truncated_current_feed_recovers_parent_risk(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "remote" / "system.json"
            path.parent.mkdir()
            path.write_text("{", encoding="utf-8")
            recovered = json.dumps({"risk": {"score": 91, "level": "red", "external_risk": 1}})
            with patch("scripts.update_system.subprocess.run", return_value=subprocess.CompletedProcess([], 0, recovered, "")) as run:
                risk, warning = load_previous_risk(path)
            self.assertEqual(risk["score"], 91)
            self.assertIn("上一個 Git 版本", warning)
            self.assertEqual(run.call_args.args[0], ["git", "show", "HEAD^:remote/system.json"])

    def test_missing_backup_returns_warning_instead_of_crashing(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "system.json"
            path.write_text("", encoding="utf-8")
            with patch("scripts.update_system.subprocess.run", side_effect=subprocess.CalledProcessError(128, ["git", "show"])):
                risk, warning = load_previous_risk(path)
            self.assertEqual(risk, {})
            self.assertIn("都無法解析", warning)


if __name__ == "__main__":
    unittest.main()
