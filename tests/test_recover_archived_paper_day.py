"""Tests for replaying immutable missed paper days without look-ahead."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.recover_archived_paper_day import recover_pending
from scripts.update_paper_performance import initial_state

DAY1 = "2026-10-21"
DAY2 = "2026-10-22"


def archive(day, base):
    quotes = {f"{1000+i:04d}": float(base+i) for i in range(600)}
    quotes["2330"] = float(base)
    return {"schema": 1, "kind": "official_daily_close", "data_date": day,
            "coverage_count": len(quotes), "days": {day: quotes}}


def snapshot(day=DAY2, captured_at="2026-10-22 20:22"):
    return {"schema_version": 1, "data_date": day, "captured_at": captured_at,
            "picks": [
                {"as_of": day, "code": "2330", "cohort": "momentum", "name": "台積電", "signal_score": 90},
                {"as_of": day, "code": "2317", "cohort": "monster", "name": "鴻海", "signal_score": 80},
                {"as_of": day, "code": "2344", "cohort": "pre_breakout", "name": "華邦電"},
            ]}


class RecoverArchivedPaperDayTests(unittest.TestCase):
    def prepare(self, root):
        snap_dir = root / "data/pick_snapshots"
        close_dir = root / "data/feed_closes"
        snap_dir.mkdir(parents=True)
        close_dir.mkdir(parents=True)
        (snap_dir / f"{DAY2}.json").write_text(json.dumps(snapshot()), encoding="utf-8")
        for day, base in [(DAY1, 100), (DAY2, 106)]:
            (close_dir / f"{day}.json").write_text(json.dumps(archive(day, base)), encoding="utf-8")
        state = initial_state()
        state["last_processed_day"] = DAY1
        state["signals"] = [{"id": DAY1+":2330", "day": DAY1, "code": "2330",
                             "name": "台積電", "score": 90, "source": "attack",
                             "signal_close": 100.0}]
        return state, snap_dir, close_dir

    def test_replays_only_the_next_archived_close_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            state, snap_dir, close_dir = self.prepare(Path(temp))
            self.assertEqual(recover_pending(state, snap_dir, close_dir), 1)
            self.assertEqual(state["last_processed_day"], DAY2)
            self.assertEqual(state["latest_signal_count"], 2)
            for account in state["strategies"].values():
                self.assertTrue(any(p["code"] == "2330" and p["entry_day"] == DAY2 for p in account["positions"]))
            before = copy.deepcopy(state)
            self.assertEqual(recover_pending(state, snap_dir, close_dir), 0)
            self.assertEqual(state, before)

    def test_refuses_missing_previous_session_without_mutating_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snap_dir = root / "snapshots"
            close_dir = root / "closes"
            snap_dir.mkdir()
            close_dir.mkdir()
            (snap_dir / f"{DAY2}.json").write_text(json.dumps(snapshot()), encoding="utf-8")
            (close_dir / f"{DAY2}.json").write_text(json.dumps(archive(DAY2, 106)), encoding="utf-8")
            state = initial_state()
            state["last_processed_day"] = DAY1
            before = copy.deepcopy(state)
            with self.assertRaisesRegex(ValueError, "缺口"):
                recover_pending(state, snap_dir, close_dir)
            self.assertEqual(state, before)

    def test_refuses_wrong_capture_date_or_preclose_time(self):
        with tempfile.TemporaryDirectory() as temp:
            state, snap_dir, close_dir = self.prepare(Path(temp))
            bad = snapshot(captured_at="2026-10-22 13:29")
            (snap_dir / f"{DAY2}.json").write_text(json.dumps(bad), encoding="utf-8")
            before = copy.deepcopy(state)
            with self.assertRaises(ValueError):
                recover_pending(state, snap_dir, close_dir)
            self.assertEqual(state, before)


if __name__ == "__main__":
    unittest.main()
