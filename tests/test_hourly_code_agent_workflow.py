"""Static safety checks for the opt-in hourly JEI code agent."""
from pathlib import Path
import unittest

WORKFLOW = Path(".github/workflows/jei-hourly-code-agent.yml")
PROMPT = Path(".github/jei/hourly-coding-task.md")


class HourlyCodeAgentWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.prompt = PROMPT.read_text(encoding="utf-8")
        cls.guard, rest = cls.workflow.split("\n  propose:\n", 1)
        cls.propose, rest = rest.split("\n  validate:\n", 1)
        cls.validate, cls.publisher = rest.split("\n  open_pr:\n", 1)

    def test_explicit_optin_and_no_duplicate_hourly_pr(self):
        self.assertIn("cron: '23 * * * *'", self.guard)
        self.assertIn("JEI_CODING_AGENT_ENABLED", self.guard)
        self.assertIn('!= "true"', self.guard)
        self.assertIn("AGENT_BLOCKED", self.guard)
        self.assertIn('startsWith', self.guard.replace("startswith", "startsWith"))
        self.assertIn("AGENT_PAUSED", self.guard)
        self.assertIn("if: needs.guard.outputs.eligible == 'true'", self.propose)

    def test_agent_has_no_repository_write_token_or_live_deploy(self):
        self.assertIn("contents: read", self.propose)
        self.assertIn("persist-credentials: false", self.propose)
        self.assertIn("uses: openai/codex-action@v1", self.propose)
        self.assertIn("openai-api-key: ${{ secrets.OPENAI_API_KEY }}", self.propose)
        self.assertIn("permission-profile: ':workspace'", self.propose)
        self.assertNotIn("contents: write", self.propose)
        self.assertNotIn("git push", self.propose)
        self.assertNotIn("gh pr create", self.propose)
        self.assertNotIn("OPENAI_API_KEY:", self.guard + self.validate + self.publisher)

    def test_patch_scope_validation_separate_from_privileged_publish(self):
        self.assertIn("needs: propose", self.validate)
        self.assertIn("git apply --check", self.validate)
        self.assertIn("Unsafe generated file", self.validate)
        self.assertIn("File deletion is not permitted", self.validate)
        self.assertIn("test_early_index_crash_alert.py", self.validate)
        self.assertIn("tests/dashboard_smoke.test.cjs", self.validate)
        self.assertIn("needs: [propose, validate]", self.publisher)
        self.assertIn("contents: write", self.publisher)
        self.assertIn("pull-requests: write", self.publisher)
        self.assertNotIn("codex-action", self.publisher)
        self.assertIn("gh pr create", self.publisher)
        self.assertNotIn("gh pr merge", self.publisher)
        self.assertNotIn("git push --force", self.publisher)

    def test_prompt_requires_real_bug_and_forbids_fake_progress(self):
        for fragment in ("reproducible", "regression tests",
                         "Leave the checkout unchanged",
                         "No dependency installation",
                         "Never delete source files"):
            self.assertIn(fragment, self.prompt)
        self.assertNotIn("OPENAI_API_KEY", self.prompt)


if __name__ == "__main__":
    unittest.main()
