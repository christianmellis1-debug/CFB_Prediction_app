"""Guard against slow network fetches returning to eager Game Cards rendering."""
import ast
from pathlib import Path
import unittest


APP = Path(__file__).resolve().parents[1] / "app.py"


class RedZoneLazyLoadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = APP.read_text()
        cls.tree = ast.parse(cls.source)

    def test_redzone_is_fetched_only_under_explicit_button(self):
        calls = []
        def walk(node, ancestors=()):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in {"red_zone_team_index", "red_zone_matchup_html"}:
                    calls.append((node.func.id, node.lineno, ancestors))
            for child in ast.iter_child_nodes(node):
                walk(child, ancestors + (node,))
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue  # helper definitions are not part of eager top-level app execution
            walk(node)
        self.assertEqual({name for name, _, _ in calls},
                         {"red_zone_team_index", "red_zone_matchup_html"})
        self.assertEqual(len(calls), 2)
        for name, line, ancestors in calls:
            gated = any(
                isinstance(parent, ast.If)
                and isinstance(parent.test, ast.Call)
                and isinstance(parent.test.func, ast.Attribute)
                and parent.test.func.attr == "button"
                for parent in ancestors
            )
            self.assertTrue(gated, f"{name} on line {line} must be gated by a button")

    def test_details_remain_available_and_predictions_untouched(self):
        self.assertIn('with st.expander("Details", expanded=False):', self.source)
        self.assertIn('"Load red-zone touchdown comparison"', self.source)
        self.assertIn("red_zone_matchup_html(", self.source)
        self.assertNotIn("Checking red-zone matchup data...", self.source)
        self.assertIn('pred = add_waterfall_value(', self.source)
        self.assertIn("with risky_tab:", self.source)
        self.assertIn('with st.expander("More filters · results, odds & team data"', self.source)


if __name__ == "__main__":
    unittest.main()
