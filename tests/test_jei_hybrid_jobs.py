import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock
from tools.jei_hybrid_jobs import JobStore, job_key, LEASE_SECONDS, RETRY_SECONDS
from tools.jei_hybrid_audit import run_audit
import json

class HybridJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "jobs.sqlite3"
        self.store = JobStore(self.path)
        self.key = job_key(b"public", "qwen3:4b", "v1")

    def test_simultaneous_claim_single_winner(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.store.claim(self.key, now=100), range(8)))
        self.assertEqual(sum(s=="claimed" for s,_ in results), 1)
        self.assertEqual(sum(s=="busy" for s,_ in results), 7)

    def test_expired_claim_resumes_and_fences_old_worker(self):
        _, old = self.store.claim(self.key, now=100)
        restarted = JobStore(self.path)
        _, new = restarted.claim(self.key, now=100+LEASE_SECONDS)
        self.assertNotEqual(old, new)
        self.assertFalse(self.store.finish(self.key, old, "stale", now=221))
        self.assertFalse(self.store.fail(self.key, old, now=221))
        self.assertTrue(restarted.finish(self.key, new, "new result", now=221))
        self.assertEqual(JobStore(self.path).claim(self.key, now=222), ("cached","new result"))

    def test_expired_owner_cannot_finish_without_replacement(self):
        _, token = self.store.claim(self.key, now=100)
        self.assertFalse(self.store.finish(self.key, token, "late", now=100+LEASE_SECONDS))

    def test_retry_cooldown_and_limit(self):
        now=100
        for _ in range(3):
            status,token=self.store.claim(self.key, now=now)
            self.assertEqual(status, "claimed")
            self.assertTrue(self.store.fail(self.key, token, now=now+1))
            self.assertEqual(self.store.claim(self.key, now=now+2)[0], "busy")
            now += RETRY_SECONDS+1
        self.assertEqual(self.store.claim(self.key, now=now)[0], "exhausted")

    def test_source_model_engine_isolation(self):
        for key in (job_key(b"changed","qwen3:4b","v1"),
                    job_key(b"public","qwen3:8b","v1"),
                    job_key(b"public","qwen3:4b","v2")):
            self.assertNotEqual(key,self.key)
        status,token=self.store.claim(self.key,now=100)
        self.assertTrue(self.store.finish(self.key,token,"valid",now=101))
        self.assertEqual(self.store.claim(job_key(b"changed","qwen3:4b","v1"),now=102)[0],"claimed")

    def test_audit_reuses_persistent_summary_after_restart(self):
        raw=json.dumps({"latest_official_day":"2026-11-26","groups":{"test":{"3":{
            "completed":30,"win_rate_pct":40,"avg_estimated_net_pct":-1}}}}).encode()
        summary=Mock(return_value="測試")
        first=run_audit(raw,enabled=True,local_available=True,job_store=self.store,summarize=summary)
        second=run_audit(raw,enabled=True,local_available=True,job_store=JobStore(self.path),summarize=summary)
        self.assertEqual(first["observed"],second["observed"])
        self.assertEqual(first["narrative_source"],"model")
        self.assertEqual(second["narrative_source"],"cache")
        self.assertEqual(summary.call_count,1)

    def test_invalid_result_rejected(self):
        _,token=self.store.claim(self.key,now=100)
        for invalid in ("", "   ", 123, "a"*4001):
            with self.assertRaises(ValueError):
                self.store.finish(self.key,token,invalid,now=101)
        self.assertEqual(self.store.claim(self.key,now=102)[0],"busy")
