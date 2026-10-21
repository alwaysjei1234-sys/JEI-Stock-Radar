"""Regression: industry evidence labels must not replace the overall market risk label."""
import ast
import pathlib
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "update_system.py"


class RiskResearchLabelTests(unittest.TestCase):
    def test_research_loop_never_assigns_market_label(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        loops = [node for node in ast.walk(tree) if isinstance(node, ast.For)
                 and isinstance(node.target, ast.Name) and node.target.id == "x"
                 and isinstance(node.iter, ast.Name) and node.iter.id == "future_monster"]
        self.assertEqual(len(loops), 1)
        assignments = [target.id for node in ast.walk(loops[0]) if isinstance(node, ast.Assign)
                       for target in node.targets if isinstance(target, ast.Name)]
        self.assertIn("research_label", assignments)
        self.assertNotIn("label", assignments)


if __name__ == "__main__":
    unittest.main()
