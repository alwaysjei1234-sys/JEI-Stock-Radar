import json
import unittest
from unittest.mock import Mock
from tools.jei_hybrid_audit import run_audit

RAW = json.dumps({"latest_official_day": "2026-11-26", "groups": {
    "test": {"3": {"completed": 30, "win_rate_pct": 40, "avg_estimated_net_pct": -1},
             "7": {"completed": 31, "win_rate_pct": 60, "avg_estimated_net_pct": 2}}}}).encode()
FRESH = {"status": "RECENT_HEARTBEAT", "drive_access": "authenticated"}
STALE = {"status": "STALE", "drive_access": "authenticated"}

class HybridAuditTests(unittest.TestCase):
    def test_ten_switches_preserve_deterministic_result(self):
        summary = Mock(return_value="測試文字")
        baseline = run_audit(RAW)
        self.assertEqual(baseline["observed"]["eligible_aggregates"], 2)
        self.assertEqual(baseline["observed"]["underperforming_aggregates"], 1)
        for _ in range(10):
            for local, watchdog, expected in (
                (True, FRESH, "local_candidate"),
                (False, FRESH, "colab_candidate"),
                (False, STALE, "existing_cloud_pipeline"),
                (False, None, "existing_cloud_pipeline")):
                with self.subTest(local=local, watchdog=watchdog):
                    result = run_audit(RAW, enabled=True, local_available=local,
                                       watchdog=watchdog, summarize=summary)
                    self.assertEqual(result["routing_candidate"], expected)
                    self.assertEqual(result["observed"], baseline["observed"])
                    self.assertFalse(result["dispatch_performed"])
        self.assertEqual(summary.call_count, 10)

    def test_local_disconnect_retains_audit(self):
        summary = Mock(side_effect=TimeoutError())
        for watchdog, expected in ((FRESH, "colab_candidate"), (STALE, "existing_cloud_pipeline")):
            result = run_audit(RAW, enabled=True, local_available=True,
                               watchdog=watchdog, summarize=summary)
            self.assertEqual(result["routing_candidate"], expected)
            self.assertEqual(result["narrative_status"], "local_failed_deterministic_audit_retained")
            self.assertEqual(result["observed"], run_audit(RAW)["observed"])

    def test_colab_ack_requires_matching_id_and_freshness(self):
        ack = {"task_id": run_audit(RAW)["task_id"], "status": "completed", "observed_only": True}
        for watchdog, expected in ((FRESH, True), (STALE, False)):
            result = run_audit(RAW, enabled=True, watchdog={**watchdog, "colab_task_result": ack})
            self.assertEqual(result["colab_ack"] is not None, expected)
        result = run_audit(RAW, enabled=True, watchdog={**FRESH, "colab_task_result": {
            **ack, "task_id": "observed-2026-11-25"}})
        self.assertIsNone(result["colab_ack"])

    def test_disabled_never_invokes_model(self):
        summary = Mock()
        run_audit(RAW, enabled=False, local_available=True, watchdog=FRESH, summarize=summary)
        summary.assert_not_called()

    def test_bad_input(self):
        for raw in (b"{}", b"not json", b"x"*2_000_001):
            with self.assertRaises(ValueError):
                run_audit(raw)
