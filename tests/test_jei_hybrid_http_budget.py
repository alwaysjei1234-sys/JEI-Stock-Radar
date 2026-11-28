"""Synthetic HTTP bodies and clocks only; no live model or user PC access."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import jei_local_ai_router as router
from tools.jei_hybrid_audit import run_audit, local_summary
from tools import jei_hybrid_worker as worker


class Clock:
    value = 0
    def now(self):
        return self.value


class Drip(io.BytesIO):
    def __init__(self, body, clock, step):
        super().__init__(body)
        self.clock, self.step = clock, step
    def read(self, size=-1):
        self.clock.value += 100
        return super().read(size)
    def read1(self, size=-1):
        self.clock.value += self.step
        return io.BytesIO.read(self, 1)


class HybridHttpBudgetTests(unittest.TestCase):
    tags = json.dumps({'models':[{'name':router.MODEL}]}).encode()

    def test_probe_slow_success_cannot_exceed_attempt_budget(self):
        clock = Clock(); response = Drip(self.tags, clock, 1)
        with patch('time.monotonic', side_effect=clock.now), \
             patch.object(router, 'build_opener') as opener:
            opener.return_value.open.return_value = response
            self.assertFalse(router.local_ready())
        self.assertTrue(response.closed)

    def test_connection_time_counts_towards_probe_budget(self):
        clock = Clock(); response = io.BytesIO(self.tags)
        def connect(*args, **kwargs):
            clock.value += 3
            return response
        with patch('time.monotonic', side_effect=clock.now), \
             patch.object(router, 'build_opener') as opener:
            opener.return_value.open.side_effect = connect
            self.assertFalse(router.local_ready())
        self.assertTrue(response.closed)

    def test_fast_probe_preserves_installed_model_detection(self):
        response = io.BytesIO(self.tags)
        with patch.object(router, 'build_opener') as opener:
            opener.return_value.open.return_value = response
            self.assertTrue(router.local_ready())
        self.assertTrue(response.closed)

    def test_truncated_body_is_rejected_even_when_json_parses(self):
        class Truncated(io.BytesIO):
            def getheader(self, name):
                return str(len(HybridHttpBudgetTests.tags) + 10)
        with patch.object(router, 'build_opener') as opener:
            opener.return_value.open.return_value = Truncated(self.tags)
            self.assertFalse(router.local_ready())

    def test_slow_summary_keeps_deterministic_audit_and_fallback(self):
        raw = json.dumps({'latest_official_day':'2026-11-27','groups':{
            'test':{'3':{'completed':30,'win_rate_pct':40,'avg_estimated_net_pct':-1}}}}).encode()
        baseline = run_audit(raw)['observed']
        body = json.dumps({'model':router.MODEL,'done':True,
                           'message':{'content':'合成測試摘要'}}).encode()
        clock = Clock(); response = Drip(body, clock, 30)
        with patch('time.monotonic', side_effect=clock.now), \
             patch('tools.jei_hybrid_audit.build_opener') as opener:
            opener.return_value.open.return_value = response
            result = run_audit(raw, enabled=True, local_available=True, summarize=local_summary)
        self.assertEqual(result['observed'], baseline)
        self.assertEqual(result['narrative_status'], 'local_failed_deterministic_audit_retained')
        self.assertEqual(result['routing_candidate'], 'existing_cloud_pipeline')
        self.assertNotIn('narrative', result)
        self.assertTrue(response.closed)


class PublicWorkerHttpBudgetTests(unittest.TestCase):
    def test_timeout_at_either_snapshot_read_is_retryable_without_receipt(self):
        from tools.jei_colab_coordination import task_from_picks
        data = {'latest_official_day':'2026-11-27','groups':{
            'attack':{'3':{'completed':30,'win_rate_pct':40,'avg_estimated_net_pct':-1}}}}
        body = json.dumps(data).encode()
        signal = {'task':task_from_picks(data, versioned=True)}
        for phase in ('initial', 'recheck'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as tmp:
                clock = Clock(); slow = Drip(body, clock, 5)
                responses = [slow] if phase == 'initial' else [io.BytesIO(body), slow]
                with patch('time.monotonic', side_effect=clock.now), \
                     patch.object(worker, 'build_opener') as opener:
                    opener.return_value.open.side_effect = responses
                    result = worker.pull_once(output_dir=Path(tmp)/'receipts',
                        job_db=Path(tmp)/'jobs.db', reader=lambda:signal,
                        fetcher=worker.fetch_public_picks)
                self.assertEqual(result['status'], 'retry_later')
                self.assertEqual(result['error_type'], 'TimeoutError')
                self.assertFalse((Path(tmp)/'receipts').exists())
                self.assertTrue(slow.closed)

    def test_slow_public_body_is_rejected_and_closed(self):
        clock = Clock(); response = Drip(b'{"groups":{}}', clock, 5)
        with patch('time.monotonic', side_effect=clock.now), \
             patch.object(worker, 'build_opener') as opener:
            opener.return_value.open.return_value = response
            with self.assertRaises(TimeoutError):
                worker.fetch_public_picks()
        self.assertTrue(response.closed)

    def test_connection_time_counts_before_public_body_read(self):
        clock = Clock(); response = io.BytesIO(b'{}')
        def connect(*args, **kwargs):
            clock.value += 21
            return response
        with patch('time.monotonic', side_effect=clock.now), \
             patch.object(worker, 'build_opener') as opener:
            opener.return_value.open.side_effect = connect
            with self.assertRaises(TimeoutError):
                worker.fetch_public_picks()
        self.assertTrue(response.closed)

    def test_fast_public_body_is_preserved(self):
        body = b'{"groups":{}}'; response = io.BytesIO(body)
        with patch.object(worker, 'build_opener') as opener:
            opener.return_value.open.return_value = response
            self.assertEqual(worker.fetch_public_picks(), body)
        self.assertTrue(response.closed)

    def test_public_size_cap_is_enforced_by_transport(self):
        response = io.BytesIO(b'x' * (worker.MAX_BYTES + 1))
        with patch.object(worker, 'build_opener') as opener:
            opener.return_value.open.return_value = response
            with self.assertRaises(ValueError):
                worker.fetch_public_picks()
        self.assertTrue(response.closed)
