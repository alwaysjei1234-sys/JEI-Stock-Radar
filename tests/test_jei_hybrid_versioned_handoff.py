"""Versioned handoff regression: simulated transport, real production code."""
import copy
import datetime as dt
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.jei_colab_coordination import (
    merge_status, task_from_picks, publish_matches_current_snapshot,
)
from tools.jei_colab_heartbeat import (
    audit_observed_picks, heartbeat_payload, read_github_coordination,
    retain_current_task_result, write_heartbeat,
)
from tools.jei_drive_heartbeat_ingest import ingest
from tools.jei_hybrid_audit import run_audit

DAY = "2026-11-26"
NOW = dt.datetime.now(dt.timezone.utc)

def picks_for(n=40):
    return {"latest_official_day": DAY, "groups": {"attack": {"3": {
        "completed": n, "win_rate_pct": 25.0, "avg_estimated_net_pct": -2.5}}}}

def raw(picks):
    return json.dumps(picks).encode("utf-8")

class VersionedHandoffTests(unittest.TestCase):
    def test_ten_same_day_revisions_roundtrip(self):
        previous = None
        previous_work = None
        seen = set()
        with tempfile.TemporaryDirectory() as folder:
            for i in range(10):
                picks = picks_for(40 + i)
                now = NOW + dt.timedelta(seconds=i)
                offered = merge_status(None, previous=previous, now=now,
                                       picks=picks, versioned=True)
                task = offered["colab_task"]
                self.assertNotIn(task["task_id"], seen)
                seen.add(task["task_id"])
                self.assertIsNone(retain_current_task_result(previous_work, task))
                with patch("urllib.request.urlopen", return_value=io.BytesIO(raw(offered))):
                    self.assertEqual(read_github_coordination()["task"], task)
                work = audit_observed_picks(task, fetcher=lambda: raw(picks))
                heartbeat = heartbeat_payload("simulated-session", "a"*40, now=NOW)
                heartbeat.update(colab_task_result=work, actions_request="review_pick_quality")
                path = Path(folder)/"heartbeat.json"
                write_heartbeat(path, heartbeat)
                with patch("tools.jei_drive_heartbeat_ingest.download_heartbeat",
                           return_value=json.loads(path.read_text())):
                    watchdog = ingest("fixture", "fixture", Path(folder)/"watchdog.json")
                reviewed = merge_status(watchdog, offered, now=now, picks=picks,
                                        versioned=True)
                self.assertEqual(reviewed["colab_task_ack"]["task_id"], task["task_id"])
                self.assertEqual(reviewed["colab_requested_audit"], "review_pick_quality")
                hybrid = run_audit(raw(picks), enabled=True, watchdog=watchdog)
                self.assertEqual(hybrid["task_id"], task["task_id"])
                self.assertEqual(hybrid["colab_ack"], reviewed["colab_task_ack"])
                self.assertEqual(hybrid["observed"], work)
                self.assertTrue(publish_matches_current_snapshot(reviewed, previous, picks))
                if previous is not None:
                    self.assertFalse(publish_matches_current_snapshot(previous, reviewed, picks))
                previous, previous_work = reviewed, work
        self.assertEqual(len(seen), 10)

    def test_same_day_mutation_rejects_old_task_and_ack(self):
        original, changed = picks_for(), picks_for(41)
        task = task_from_picks(original, versioned=True)
        with self.assertRaisesRegex(ValueError, "official_snapshot_changed"):
            audit_observed_picks(task, fetcher=lambda: raw(changed))
        watchdog = {"status":"RECENT_HEARTBEAT", "drive_access":"authenticated",
                    "colab_task_result":audit_observed_picks(task, fetcher=lambda: raw(original)),
                    "colab_request":"review_pick_quality"}
        result = merge_status(watchdog, picks=changed, versioned=True)
        self.assertIsNone(result["colab_task_ack"])
        self.assertIsNone(result["colab_requested_audit"])
        self.assertIsNone(run_audit(raw(changed), enabled=True, watchdog=watchdog)["colab_ack"])

    def test_legacy_ack_cannot_authorize_versioned_review(self):
        picks = picks_for()
        legacy = audit_observed_picks(task_from_picks(picks), fetcher=lambda: raw(picks))
        watchdog = {"status":"RECENT_HEARTBEAT", "drive_access":"authenticated",
                    "colab_task_result":legacy, "colab_request":"review_pick_quality"}
        result = merge_status(watchdog, picks=picks, versioned=True)
        self.assertIsNone(result["colab_task_ack"])
        self.assertIsNone(result["colab_requested_audit"])

    def test_digest_stable_for_key_order_and_metadata(self):
        picks = picks_for()
        other = {"groups": copy.deepcopy(picks["groups"]), "latest_official_day": DAY,
                 "updated_at":"irrelevant"}
        self.assertEqual(task_from_picks(picks, versioned=True),
                         task_from_picks(other, versioned=True))

    def test_old_state_cannot_replace_newer_state_same_snapshot(self):
        picks = picks_for()
        old = merge_status(None, now=NOW, picks=picks, versioned=True)
        new = merge_status({"status":"STALE","drive_access":"authenticated"},
                           now=NOW+dt.timedelta(minutes=1), picks=picks, versioned=True)
        self.assertFalse(publish_matches_current_snapshot(old, new, picks))
        self.assertTrue(publish_matches_current_snapshot(new, old, picks))
        self.assertTrue(publish_matches_current_snapshot(new, new, picks))
        self.assertFalse(publish_matches_current_snapshot(
            {**new,"status_changed_at_utc":"invalid"}, old, picks))

    def test_invalid_or_untrusted_versioned_task_not_dispatched(self):
        picks = picks_for()
        signal = merge_status(None, picks=picks, versioned=True)
        signal["colab_task"]["task_id"] = "observed-"+DAY+"-bad"
        with patch("urllib.request.urlopen", return_value=io.BytesIO(raw(signal))):
            self.assertNotIn("task", read_github_coordination())
        picks["groups"]["attack"]["3"]["win_rate_pct"] = float("nan")
        self.assertIsNone(task_from_picks(picks, versioned=True))
