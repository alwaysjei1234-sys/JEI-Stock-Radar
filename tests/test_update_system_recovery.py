import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.update_system import load_previous_risk, retain_same_session_composite_risk


class PreviousRiskRecoveryTests(unittest.TestCase):
    def test_only_same_session_valid_composite_can_raise_score(self):
        today = "2026-11-16"
        valid = {"score": 91, "level": "red", "as_of": today, "external_risk": 1}
        self.assertEqual(retain_same_session_composite_risk(30, valid, today), 91)
        self.assertEqual(retain_same_session_composite_risk(97, valid, today), 97)
        for changes in (
            {"as_of": "2026-11-13"}, {"as_of": "2026-11-17"}, {"as_of": None},
            {"actionable": False}, {"external_risk": None}, {"score": float("nan")},
            {"score": float("inf")}, {"score": 101}, {"score": "unknown"},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(retain_same_session_composite_risk(30, {**valid, **changes}, today), 30)

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
            command = run.call_args.args[0]
            self.assertEqual(command[:2], ["git", "show"])
            self.assertTrue(command[2].endswith("/remote/system.json"))

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
