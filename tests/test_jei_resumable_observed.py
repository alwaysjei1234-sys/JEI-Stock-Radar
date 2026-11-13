import json
import tempfile
import unittest
from pathlib import Path
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
