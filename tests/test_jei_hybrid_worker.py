import json
from contextlib import nullcontext
from http.client import IncompleteRead, BadStatusLine
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
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

    def test_http_protocol_failures_retry_without_receipt(self):
        d = data()
        for error in (IncompleteRead(b"partial"), BadStatusLine("bad response")):
            with self.subTest(error=type(error).__name__):
                result = pull_once(**self.defaults, reader=lambda:signal(d),
                                   fetcher=Mock(side_effect=error))
                self.assertEqual(result["status"], "retry_later")
                self.assertEqual(result["error_type"], type(error).__name__)
                self.assertFalse(self.defaults["output_dir"].exists())

    def test_model_probe_protocol_failure_uses_deterministic_fallback(self):
        from jei_local_ai_router import local_ready
        d = data()
        with patch("jei_local_ai_router.build_opener") as opener:
            opener.return_value.open.side_effect = BadStatusLine("bad response")
            result = pull_once(**self.defaults, reader=lambda:signal(d),
                               fetcher=lambda:raw(d), enable_local=True, probe=local_ready)
        self.assertEqual(result["status"], "receipt_saved")
        receipt = json.loads(Path(result["receipt"]).read_text())
        self.assertEqual(receipt["observed"]["eligible_aggregates"], 1)
        self.assertEqual(receipt["routing_candidate"], "existing_cloud_pipeline")
        self.assertNotIn("narrative", receipt)

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

class FailureStageTests(unittest.TestCase):
    """Report fixed boundary codes without copying network/path exception text."""
    def check_failure(self, readers, fetchers, stage, *, receipt_error=False):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / 'receipts'
            with patch('tools.jei_hybrid_worker.atomic_receipt',
                       side_effect=OSError('SECRET_PATH')) if receipt_error else nullcontext():
                result = pull_once(output_dir=folder, job_db=Path(td) / 'jobs.db',
                    reader=Mock(side_effect=readers), fetcher=Mock(side_effect=fetchers))
            self.assertEqual(result['status'], 'retry_later')
            self.assertEqual(result.get('error_stage'), stage)
            self.assertFalse(result['uploaded'])
            self.assertNotIn('SECRET', json.dumps(result))
            self.assertFalse(folder.exists())

    def test_initial_read_boundary_is_distinguishable(self):
        from urllib.error import URLError
        d = data()
        self.check_failure([URLError('SECRET_HOST')], [], 'coordination_read')
        self.check_failure([signal(d)], [URLError('SECRET_HOST')], 'snapshot_fetch')

    def test_recheck_read_boundary_is_distinguishable(self):
        from urllib.error import URLError
        d = data()
        self.check_failure([signal(d), URLError('SECRET_HOST')], [raw(d)],
                           'coordination_recheck')
        self.check_failure([signal(d), signal(d)], [raw(d), URLError('SECRET_HOST')],
                           'snapshot_recheck')

    def test_receipt_storage_failure_does_not_leak_path(self):
        d = data()
        self.check_failure([signal(d), signal(d)], [raw(d), raw(d)],
                           'receipt_write', receipt_error=True)
