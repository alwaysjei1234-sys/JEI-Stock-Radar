import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from concurrent.futures import ThreadPoolExecutor
from tools.jei_colab_coordination import task_from_picks
from tools.jei_hybrid_worker import pull_once, atomic_receipt

def data(n=40, **metadata):
    return {"latest_official_day":"2026-11-26","groups":{"attack":{"3":{
        "completed":n,"win_rate_pct":25,"avg_estimated_net_pct":-2.5}}}, **metadata}

def raw(d):
    return json.dumps(d).encode()

def signal(d):
    return {"state":"STALE","task":task_from_picks(d,versioned=True)}

class PullWorkerTests(unittest.TestCase):
    def setUp(self):
        root=tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.folder=Path(root.name)
        self.defaults={"output_dir":self.folder/"receipts","job_db":self.folder/"jobs.db"}

    def test_pull_public_task_without_model(self):
        d=data()
        probe=Mock(return_value=True)
        summarize=Mock()
        result=pull_once(**self.defaults,reader=lambda:signal(d),fetcher=lambda:raw(d),
                         probe=probe,summarize=summarize)
        self.assertEqual(result["status"],"receipt_saved")
        self.assertFalse(result["uploaded"])
        receipt=json.loads(Path(result["receipt"]).read_text())
        self.assertEqual(receipt["task_id"],signal(d)["task"]["task_id"])
        self.assertEqual(receipt["observed"]["eligible_aggregates"],1)
        self.assertNotIn("narrative",receipt)
        probe.assert_not_called()
        summarize.assert_not_called()

    def test_local_reconnect_reuses_result_despite_timestamp_change(self):
        d=data(updated_at="first")
        summary=Mock(return_value="測試摘要")
        opts={**self.defaults,"enable_local":True,"probe":lambda:True,"summarize":summary}
        first=pull_once(**opts,reader=lambda:signal(d),fetcher=lambda:raw(d))
        later=data(updated_at="later")
        second=pull_once(**opts,reader=lambda:signal(later),fetcher=lambda:raw(later))
        self.assertEqual(first["status"],"receipt_saved")
        self.assertEqual(second["status"],"receipt_saved")
        self.assertEqual(first["receipt"],second["receipt"])
        self.assertEqual(second["narrative_source"],"cache")
        self.assertEqual(summary.call_count,1)

    def test_legacy_and_mismatched_tasks_never_compute(self):
        d=data()
        summary=Mock()
        for task in (task_from_picks(d),signal(data(41))["task"],
                     {"kind":"execute","command":"unexpected"}):
            result=pull_once(**self.defaults,reader=lambda:{"task":task},
                             fetcher=lambda:raw(d),enable_local=True,
                             probe=lambda:True,summarize=summary)
            self.assertEqual(result["status"],"snapshot_mismatch_or_legacy_task")
        summary.assert_not_called()
        self.assertFalse(self.defaults["output_dir"].exists())

    def test_task_superseded_during_computation(self):
        d=data()
        reader=Mock(side_effect=[signal(d),signal(data(41))])
        result=pull_once(**self.defaults,reader=reader,fetcher=lambda:raw(d))
        self.assertEqual(result["status"],"superseded")
        self.assertFalse(self.defaults["output_dir"].exists())

    def test_feed_changes_before_manifest_update(self):
        d=data()
        fetcher=Mock(side_effect=[raw(d),raw(data(41))])
        result=pull_once(**self.defaults,reader=lambda:signal(d),fetcher=fetcher)
        self.assertEqual(result["status"],"superseded")

    def test_disconnect_during_result_check_is_retryable(self):
        d=data()
        reader=Mock(side_effect=[signal(d),TimeoutError()])
        result=pull_once(**self.defaults,reader=reader,fetcher=lambda:raw(d))
        self.assertEqual(result["status"],"retry_later")
        self.assertFalse(self.defaults["output_dir"].exists())

    def test_concurrent_fallback_does_not_replace_summary(self):
        task=signal(data())["task"]["task_id"]
        result={"task_id":task,"observed":{"eligible_aggregates":1}}
        with ThreadPoolExecutor(max_workers=4) as pool:
            paths=list(pool.map(lambda n: atomic_receipt(self.folder,
                {**result,**({"narrative":"complete"} if n%2 else {})}),range(8)))
        self.assertEqual(len(set(paths)),2)
        summary=next(p for p in paths if p.name.endswith("-summary.json"))
        self.assertEqual(json.loads(summary.read_text())["narrative"],"complete")
        self.assertFalse(list(self.folder.glob("*.tmp")))

    def test_model_unavailable_does_not_claim_cloud_execution(self):
        d=data()
        result=pull_once(**self.defaults,reader=lambda:signal(d),fetcher=lambda:raw(d),
                         enable_local=True,probe=lambda:False)
        receipt=json.loads(Path(result["receipt"]).read_text())
        self.assertEqual(receipt["routing_candidate"],"existing_cloud_pipeline")
        self.assertFalse(receipt["uploaded"])
        self.assertIsNone(receipt["narrative_source"])
