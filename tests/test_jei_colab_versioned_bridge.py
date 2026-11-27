"""Versioned Colab bridge, real functions with simulated network transport."""
import datetime as dt
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools.jei_colab_coordination import merge_status, task_from_picks, publish_matches_current_snapshot
from tools.jei_colab_heartbeat import audit_observed_picks, heartbeat_payload, read_github_coordination
from tools.jei_drive_heartbeat_ingest import ingest

def picks(n=40):
    return {"latest_official_day":"2026-11-26","groups":{"attack":{"3":{
        "completed":n,"win_rate_pct":25,"avg_estimated_net_pct":-2}}}}

def raw(data):
    return json.dumps(data).encode()

def watch(ack):
    return {"status":"RECENT_HEARTBEAT","drive_access":"authenticated",
            "colab_task_result":ack,"colab_request":"review_pick_quality"}

class VersionedBridgeTests(unittest.TestCase):
    def test_ten_same_day_revisions(self):
        previous=None
        previous_ack=None
        now=dt.datetime.now(dt.timezone.utc)
        with tempfile.TemporaryDirectory() as folder:
            for i in range(10):
                data=picks(40+i)
                current=merge_status(None, picks=data, now=now+dt.timedelta(seconds=i),versioned=True)
                task=current["colab_task"]
                if previous_ack:
                    self.assertIsNone(merge_status(watch(previous_ack),picks=data,versioned=True)["colab_task_ack"])
                with patch("urllib.request.urlopen",return_value=io.BytesIO(raw(current))):
                    self.assertEqual(read_github_coordination()["task"],task)
                ack=audit_observed_picks(task,fetcher=lambda:raw(data))
                heartbeat=heartbeat_payload("fixture","a"*40,now=now)
                heartbeat.update(colab_task_result=ack,actions_request="review_pick_quality")
                with patch("tools.jei_drive_heartbeat_ingest.download_heartbeat",return_value=heartbeat):
                    status=ingest("fixture","fixture",Path(folder)/"status.json")
                result=merge_status(status,picks=data,now=now+dt.timedelta(seconds=i),versioned=True)
                self.assertTrue(result["colab_task_ack"]["aggregate_match"])
                self.assertEqual(result["colab_requested_audit"],"review_pick_quality")
                self.assertTrue(publish_matches_current_snapshot(result,previous,data))
                if previous:
                    self.assertFalse(publish_matches_current_snapshot(previous,result,data))
                previous,previous_ack=result,ack

    def test_wrong_counts_or_missing_counts_rejected(self):
        data=picks()
        task=task_from_picks(data,versioned=True)
        ack=audit_observed_picks(task,fetcher=lambda:raw(data))
        for bad in ({**ack,"eligible_aggregates":2},{**ack,"underperforming_aggregates":0},
                    {**ack,"eligible_aggregates":True},
                    {k:v for k,v in ack.items() if k!="eligible_aggregates"}):
            result=merge_status(watch(bad),picks=data,versioned=True)
            self.assertIsNone(result["colab_task_ack"])
            self.assertIsNone(result["colab_requested_audit"])

    def test_legacy_ack_not_versioned(self):
        data=picks()
        ack=audit_observed_picks(task_from_picks(data),fetcher=lambda:raw(data))
        self.assertIsNone(merge_status(watch(ack),picks=data,versioned=True)["colab_task_ack"])
        self.assertIsNotNone(merge_status(watch(ack),picks=data)["colab_task_ack"])

    def test_source_changes(self):
        with self.assertRaisesRegex(ValueError,"official_snapshot_changed"):
            audit_observed_picks(task_from_picks(picks(),versioned=True),fetcher=lambda:raw(picks(41)))

    def test_no_regression_on_stale_publish(self):
        now=dt.datetime.now(dt.timezone.utc)
        data=picks()
        old=merge_status(None,picks=data,now=now,versioned=True)
        current=merge_status({"status":"STALE","drive_access":"authenticated"},picks=data,
                             now=now+dt.timedelta(seconds=1),versioned=True)
        self.assertFalse(publish_matches_current_snapshot(old,current,data))
        self.assertTrue(publish_matches_current_snapshot(current,old,data))
        self.assertFalse(publish_matches_current_snapshot(current,old,picks(41)))
