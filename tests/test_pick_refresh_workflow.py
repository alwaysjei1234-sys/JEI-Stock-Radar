"""Successful market publications must wake immutable pick capture safely."""
from pathlib import Path
import unittest


class PickRefreshWorkflowTests(unittest.TestCase):
    def test_capture_has_market_completion_trigger_and_main_only_writer(self):
        workflow = Path('.github/workflows/refresh-pick-validation.yml').read_text()
        self.assertIn('workflow_run:', workflow)
        self.assertIn('"Update JEI Market Feed"', workflow)
        self.assertIn('"JEI Stalled Market Feed Recovery"', workflow)
        self.assertIn('types: [completed]', workflow)
        writer = workflow.split('  refresh:', 1)[1]
        self.assertIn("github.event_name != 'pull_request'", writer)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", writer)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", writer)
        self.assertIn('github.event.workflow_run.head_repository.full_name == github.repository', writer)
        self.assertIn('ref: main', writer)
        recovery = writer.index('python -m scripts.recover_pick_history --ref HEAD --write')
        update = writer.index('python -m scripts.update_pick_validation')
        publish = writer.index('git add remote/pick_validation.json remote/pick_history.json')
        self.assertLess(recovery, update)
        self.assertLess(update, publish)
        self.assertNotIn('--report-only', writer)
        self.assertIn("if: github.event_name == 'pull_request'", workflow)


if __name__ == '__main__':
    unittest.main()
