"""Network-free tests for Phase 3 matchday presentation helpers."""
import ast
from html import escape
from pathlib import Path
import unittest

import pandas as pd


APP = Path(__file__).parents[1] / "app.py"
NAMES = {"select_matchday_spotlight", "matchday_timeline_rows", "matchday_timeline_html"}


def ui_helpers():
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in NAMES]
    assert len(functions) == len(NAMES)
    namespace = {"pd": pd, "escape": escape}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(APP), "exec"), namespace)
    return namespace


class MatchdayUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helpers = ui_helpers()

    def picks(self):
        return pd.DataFrame([
            {"Game ID": 1, "Home Team": "Bears", "Away Team": "Wolves",
             "Predicted Winner": "Bears", "Confidence": .95, "Status": "Final",
             "Game of Week": False, "Game of Week Tier Count": 0, "Value Selected": False,
             "Value Rank": 0},
            {"Game ID": 2, "Home Team": "Tigers", "Away Team": "Eagles",
             "Predicted Winner": "Tigers", "Confidence": .78, "Status": "Scheduled",
             "Game of Week": True, "Game of Week Tier Count": 2, "Value Selected": True,
             "Value Tier": "Tier 1: Complete Game", "Value Rank": 1},
            {"Game ID": 3, "Home Team": "Panthers", "Away Team": "Hawks",
             "Predicted Winner": "Panthers", "Confidence": .84, "Status": "In progress",
             "Game of Week": True, "Game of Week Tier Count": 3, "Value Selected": True,
             "Value Tier": "Tier 4: Parlay Bridge", "Value Rank": 2},
        ])

    def schedule(self):
        return pd.DataFrame([
            {"game_id": 1, "start_date": "2026-10-10T01:30:00Z"},  # Friday 8:30 PM CT
            {"game_id": 2, "start_date": "2026-10-10T17:00:00Z"},  # Saturday noon CT
            {"game_id": 3, "start_date": "2026-10-11T00:30:00Z"},  # Saturday 7:30 PM CT
        ])

    def test_official_cross_tier_matchup_has_priority(self):
        selected, official = self.helpers["select_matchday_spotlight"](self.picks())
        self.assertTrue(official)
        self.assertEqual(selected["Game ID"], 3)

    def test_no_official_game_of_week_uses_top_value_pick(self):
        frame = self.picks().copy()
        frame["Game of Week"] = False
        selected, consensus = self.helpers["select_matchday_spotlight"](frame)
        self.assertFalse(consensus)
        self.assertEqual(selected["Game ID"], 2)
        self.assertEqual(selected["Value Rank"], 1)
        # Finished games still use the Value Shortlist ranking, not model chance.
        frame["Status"] = "Final"
        selected, consensus = self.helpers["select_matchday_spotlight"](frame)
        self.assertFalse(consensus)
        self.assertEqual(selected["Game ID"], 2)

    def test_fallback_follows_official_rank_not_probability_or_row_order(self):
        frame = self.picks().copy()
        frame["Game of Week"] = False
        frame.loc[0, "Confidence"] = .999
        frame = frame.iloc[[2, 0, 1]].copy()
        selected, consensus = self.helpers["select_matchday_spotlight"](frame)
        self.assertFalse(consensus)
        self.assertEqual(selected["Value Rank"], 1)
        self.assertEqual(selected["Game ID"], 2)

    def test_no_official_or_value_pick_means_no_spotlight(self):
        frame = self.picks().copy()
        frame["Game of Week"] = False
        frame["Value Selected"] = False
        self.assertEqual(self.helpers["select_matchday_spotlight"](frame), (None, False))
        frame["Value Selected"] = True
        frame["Value Rank"] = 0
        self.assertEqual(self.helpers["select_matchday_spotlight"](frame), (None, False))

    def test_a_high_confidence_favorite_never_displaces_official_gotw(self):
        frame = self.picks().copy()
        frame.loc[0, "Confidence"] = .989
        selected, official = self.helpers["select_matchday_spotlight"](frame)
        self.assertTrue(official)
        self.assertEqual(selected["Game ID"], 3)

    def test_missing_official_flag_still_allows_ranked_value_fallback(self):
        frame = self.picks().drop(columns=["Game of Week"])
        selected, consensus = self.helpers["select_matchday_spotlight"](frame)
        self.assertFalse(consensus)
        self.assertEqual(selected["Value Rank"], 1)

    def test_official_game_of_week_beats_better_value_rank(self):
        frame = self.picks().copy()
        frame.loc[2, "Value Rank"] = 1
        frame.loc[1, "Value Rank"] = 2
        selected, consensus = self.helpers["select_matchday_spotlight"](frame)
        self.assertTrue(consensus)
        self.assertEqual(selected["Game ID"], 3)

    def test_empty_filters_produce_no_spotlight_or_timeline(self):
        empty = self.picks().iloc[:0]
        self.assertEqual(self.helpers["select_matchday_spotlight"](empty), (None, False))
        self.assertEqual(self.helpers["matchday_timeline_rows"](empty, self.schedule()), [])

    def test_saturday_means_saturday_in_central_time(self):
        rows = self.helpers["matchday_timeline_rows"](self.picks(), self.schedule())
        self.assertEqual([x["winner"] for x in rows], ["Tigers", "Panthers"])
        self.assertEqual([x["window"] for x in rows],
                         ["Sat, Oct 10 · 12:00 PM CT", "Sat, Oct 10 · 7:30 PM CT"])

    def test_all_days_includes_friday_and_tbd(self):
        frame = pd.concat([self.picks(), pd.DataFrame([{
            "Game ID": 4, "Home Team": "Lions", "Away Team": "Sharks",
            "Predicted Winner": "Lions", "Confidence": .6, "Status": "Scheduled",
            "Value Selected": False,
        }])], ignore_index=True)
        rows = self.helpers["matchday_timeline_rows"](frame, self.schedule(), False)
        self.assertEqual([row["winner"] for row in rows], ["Bears", "Tigers", "Panthers", "Lions"])
        self.assertEqual(rows[-1]["window"], "Kickoff time TBD")

    def test_html_escapes_user_display_data_and_shows_labels(self):
        rows = self.helpers["matchday_timeline_rows"](self.picks(), self.schedule())
        rows[0]["away"] = "<script>alert(1)</script>"
        markup = self.helpers["matchday_timeline_html"](rows)
        self.assertNotIn("<script>", markup)
        self.assertIn("&lt;script&gt;", markup)
        self.assertIn("Model chance", markup)
        self.assertIn("Tier 1: Complete Game", markup)
        self.assertIn("LIVE", markup)


if __name__ == "__main__":
    unittest.main()
