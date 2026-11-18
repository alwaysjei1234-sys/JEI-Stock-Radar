"""Guard against skipped Actions recovery events cancelling pending market updates."""
from pathlib import Path
import re
import unittest

WORKFLOW=Path(".github/workflows/recover-stale-market-feed.yml")


class MarketRecoveryConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=WORKFLOW.read_text(encoding="utf-8")
        cls.head, cls.recovery=cls.source.split("\n  recover:\n",1)

    def test_skipped_workflow_run_event_does_not_take_a_workflow_level_lock(self):
        self.assertNotRegex(self.head,r"(?m)^concurrency:\s*$")
        self.assertRegex(self.recovery,
                         r"(?m)^    concurrency:\n      group: jei-market-feed\n      cancel-in-progress: false\s*$")

    def test_recovery_lock_only_held_by_eligible_job(self):
        gate=self.recovery.split("\n    concurrency:\n",1)[0]
        self.assertIn("github.event_name != 'pull_request'",gate)
        self.assertIn("github.event.workflow_run.event == 'schedule'",gate)
        self.assertIn("github.event.workflow_run.head_branch == 'main'",gate)

    def test_independent_hourly_audit_can_trigger_stale_feed_fallback(self):
        # On 2026-11-17 the main 5-min feed stopped, while the audit ran.
        # Scheduled audit completion must be allowed to wake this watchdog.
        self.assertIn('"JEI Compute Provenance Audit (GitHub Actions)"', self.head)
        self.assertIn('"JEI Research Engine Tests"', self.head)
        audit = Path(".github/workflows/jei-colab-audit.yml").read_text(encoding="utf-8")
        self.assertIn("name: JEI Compute Provenance Audit (GitHub Actions)", audit)
        self.assertIn("cron: '37 * * * *'", audit)
        # Audit push/PR runs must NOT launch a feed rebuild.
        self.assertIn("github.event.workflow_run.event == 'schedule'", self.recovery)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", self.recovery)

    def test_verified_main_research_push_can_wake_watchdog_when_cron_stalls(self):
        gate=self.recovery.split("\n    concurrency:\n",1)[0]
        # A 2026-11-18 push-based research run must not be silently skipped
        # while GitHub's independent schedule is delayed and the feed is stale.
        self.assertIn("github.event.workflow_run.event == 'push'",gate)
        self.assertIn("github.event.workflow_run.name == 'JEI Research Engine Tests'",gate)
        # Never turn a failed upstream, PR or fork workflow into a market writer.
        self.assertIn("github.event.workflow_run.conclusion == 'success'",gate)
        self.assertIn("github.event.workflow_run.head_branch == 'main'",gate)
        self.assertIn("github.event.workflow_run.head_repository.full_name == github.repository",gate)
        self.assertIn("github.event_name != 'pull_request'",gate)
        # The scheduled audit still provides its original independent clock.
        self.assertIn("github.event.workflow_run.event == 'schedule'",gate)

    def test_research_push_wakeup_remains_stale_only(self):
        # Waking a watchdog is not permission to overwrite a healthy market feed.
        self.assertIn("if: steps.freshness.outputs.recover == 'true'",self.recovery)
        self.assertIn("python -m scripts.market_feed_watchdog --input remote/system.json",self.recovery)

    def test_healthy_no_op_still_does_not_rebuild(self):
        self.assertIn("if: steps.freshness.outputs.recover == 'true'",self.recovery)
        self.assertIn("python -m scripts.market_feed_watchdog",self.recovery)
        self.assertIn("python scripts/update_system.py",self.recovery)


if __name__=="__main__":
    unittest.main()
