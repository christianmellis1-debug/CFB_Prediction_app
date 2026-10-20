"""Network-free coverage for Saturday Forecast Market–Matchup Conflict routing."""
import ast
from pathlib import Path
import unittest
import numpy as np

from matchup_advantages import assess

APP = Path(__file__).parents[1] / "app.py"
HELPERS = {"is_market_matchup_conflict", "should_flag_risky"}


def load_helpers():
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    nodes = [x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name in HELPERS]
    assert len(nodes) == len(HELPERS), "Missing risky-pick helper"
    namespace = {"np": np, "assess": assess}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP), "exec"), namespace)
    return namespace


def record(home_advantages=1, away_advantages=4):
    # Five independent metric comparisons; lower is better for indices 2,3.
    # Home edges where home is > away for indices 0,1,4, or < for 2,3.
    # 1/4 gives home just the first edge, away all four others.
    home = [2, 1, 4, 4, 1]
    away = [1, 2, 3, 3, 2]
    if home_advantages == 4 and away_advantages == 1:
        home, away = away, home
    if home_advantages == 2 and away_advantages == 3:
        home, away = [2, 2, 4, 3, 1], [1, 1, 3, 4, 2]
    return {"status": "ok", "home": home, "away": away}


class MarketMatchupConflictTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helpers = load_helpers()
        cls.conflict = staticmethod(cls.helpers["is_market_matchup_conflict"])
        cls.risky = staticmethod(cls.helpers["should_flag_risky"])

    def test_near_tie_with_one_advantage_flags_and_enters_risky_tab_even_if_tiered(self):
        check = record()
        self.assertEqual(assess(check, "home")["count"], 1)
        self.assertEqual(assess(check, "away")["count"], 4)
        conflict = self.conflict(check, "home", True, .50037)
        self.assertTrue(conflict)
        self.assertTrue(self.risky(assess(check, "home"), True, .50037, conflict))

    def test_reverse_side_also_flags(self):
        check = record(4, 1)
        self.assertTrue(self.conflict(check, "away", True, .5075))

    def test_unrounded_confidence_boundary(self):
        check = record()
        self.assertTrue(self.conflict(check, "home", True, .51))
        self.assertFalse(self.conflict(check, "home", True, .510001))
        self.assertFalse(self.conflict(check, "home", True, .65))

    def test_no_blend_and_missing_data_do_not_trigger(self):
        self.assertFalse(self.conflict(record(), "home", False, .50037))
        self.assertFalse(self.conflict({"status":"missing"}, "home", True, .50037))
        self.assertFalse(self.conflict({"status":"outside"}, "home", True, .50037))
        self.assertFalse(self.conflict(record(), "other", True, .50037))
        self.assertFalse(self.conflict(record(), "home", True, float("nan")))
        self.assertFalse(self.conflict(record(), "home", True, None))

    def test_small_statistical_disparity_does_not_trigger(self):
        self.assertFalse(self.conflict(record(2, 3), "home", True, .505))

    def test_existing_risky_rules_remain_in_force(self):
        self.assertTrue(self.risky({"flag":True}, False, .75))
        self.assertFalse(self.risky({"flag":True}, True, .75))
        self.assertFalse(self.risky({"flag":True}, False, .80))
        self.assertFalse(self.risky(None, False, .60))
        self.assertFalse(self.risky({"flag":True}, False, float("nan")))

    def test_card_and_risky_tab_both_use_the_conflict(self):
        code = APP.read_text(encoding="utf-8")
        self.assertIn("market_conflict = is_market_matchup_conflict(", code)
        self.assertIn("market_conflict=market_conflict", code)
        self.assertIn("risky_indices.append(card_idx)", code)
        self.assertIn('render_pick_cards(pred.loc[risky_indices], "risky")', code)
        self.assertIn("Close game · conflicting signs", code)
        self.assertIn("{visible_risk}", code)
        self.assertIn("{moneylines}", code)
        self.assertIn("G6 HOME UNDERDOG · RESEARCH ONLY", code)


if __name__ == "__main__":
    unittest.main()
