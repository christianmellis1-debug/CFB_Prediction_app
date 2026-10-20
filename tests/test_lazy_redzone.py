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

    def test_unused_redzone_feeds_never_trigger_eager_card_network_calls(self):
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
        # The user removed the manual "Load" option from game cards.
        # Keep helpers available for research, but do not make calls
        # during eager page or card rendering.
        self.assertEqual(calls, [])

    def test_details_remain_available_and_predictions_untouched(self):
        self.assertIn('with st.expander("Details", expanded=False):', self.source)
        self.assertNotIn('"Load red-zone touchdown comparison"', self.source)
        self.assertIn("rushing_story_html(", self.source)
        self.assertIn("matchup_strengths_html(", self.source)
        self.assertIn("red_zone_matchup_html(", self.source)
        self.assertNotIn("Checking red-zone matchup data...", self.source)
        self.assertIn('pred = add_waterfall_value(', self.source)
        self.assertIn("with risky_tab:", self.source)
        self.assertIn('with st.expander("More filters · results, odds & team data"', self.source)


if __name__ == "__main__":
    unittest.main()
