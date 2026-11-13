import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools.jei_resumable_observed import run_batches


class ResumeTests(unittest.TestCase):
    def test_interruption_then_resume_and_idempotence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.json"
            groups = {name: {"3": {"completed": 31, "win_rate_pct": 55,
                                   "avg_estimated_net_pct": 1.2}} for name in ("attack", "monster")}
            src.write_text(json.dumps({"groups": groups}))
            checkpoint = root / "checkpoint.json"
            output = root / "output.json"
            first = run_batches(src, checkpoint, output, max_batches=1)
            self.assertFalse(first["complete"])
            self.assertEqual(first["completed_groups"], 1)
            second = run_batches(src, checkpoint, output)
            self.assertTrue(second["complete"])
            self.assertEqual(len(second["observed_rows"]), 2)
            self.assertEqual(run_batches(src, checkpoint, output)["observed_rows"], second["observed_rows"])
            self.assertFalse(second["independent_oos_verified"])

    def test_empty_group_does_not_stop_resume_of_valid_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.json"
            groups = {
                "empty": {"3": {"completed": 0, "win_rate_pct": None,
                                "avg_estimated_net_pct": None}},
                "observed": {"3": {"completed": 31, "win_rate_pct": 55,
                                   "avg_estimated_net_pct": 1.2}},
            }
            src.write_text(json.dumps({"groups": groups}))
            checkpoint, output = root / "cp.json", root / "out.json"
            partial = run_batches(src, checkpoint, output, max_batches=1)
            self.assertFalse(partial["complete"])
            self.assertEqual(partial["observed_rows"], [])
            resumed = run_batches(src, checkpoint, output)
            self.assertTrue(resumed["complete"])
            self.assertEqual(resumed["completed_groups"], 2)
            self.assertEqual([r["strategy"] for r in resumed["observed_rows"]], ["observed"])

    def test_all_empty_groups_do_not_publish_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.json"
            src.write_text(json.dumps({"groups": {"empty": {}}}))
            output = root / "out.json"
            with self.assertRaisesRegex(ValueError, "no valid completed observations"):
                run_batches(src, root / "cp.json", output)
            self.assertFalse(output.exists())

    def test_engine_change_invalidates_checkpoint_for_same_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.json"
            entry = {"completed": 31, "win_rate_pct": 55, "avg_estimated_net_pct": 1.2}
            src.write_text(json.dumps({"groups": {"a": {"3": entry}}}))
            checkpoint, output = root / "cp.json", root / "out.json"
            run_batches(src, checkpoint, output)
            engine = root / "engine.py"
            engine.write_text("# changed engine")
            with patch("tools.jei_resumable_observed.jei_shared_compute.__file__", str(engine)):
                with self.assertRaisesRegex(ValueError, "checkpoint_source_or_strategy_mismatch"):
                    run_batches(src, checkpoint, output)

    def test_source_change_invalidates_old_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.json"
            entry = {"completed": 31, "win_rate_pct": 55, "avg_estimated_net_pct": 1.2}
            src.write_text(json.dumps({"groups": {"a": {"3": entry}}}))
            run_batches(src, root / "cp.json", root / "out.json")
            src.write_text(json.dumps({"groups": {"b": {"3": entry}}}))
            with self.assertRaises(ValueError):
                run_batches(src, root / "cp.json", root / "out.json")


if __name__ == "__main__":
    unittest.main()
