"""Network-free Phase 4 Saturday Live Mode tests."""
import unittest

import pandas as pd

from matchday_live import LIVE_SECTIONS, live_board_rows, live_board_html


class SaturdayLiveModeTests(unittest.TestCase):
    def sample_predictions(self):
        return pd.DataFrame([
            {"Game ID": 1, "Away Team": "Owls", "Home Team": "Bears",
             "Predicted Winner": "Bears", "Confidence": .72, "Status": "Final",
             "Final Score": "Owls 10 – Bears 21", "Pick Result": "Correct",
             "Value Selected": True, "Value Tier": "Tier 1: Complete Game"},
            {"Game ID": 2, "Away Team": "Wolves", "Home Team": "Tigers",
             "Predicted Winner": "Tigers", "Confidence": .81, "Status": "In progress",
             "Live Detail": "3rd quarter 8:33", "Live Score": "Wolves 14 – Tigers 17",
             "Pick Result": "Pending", "Value Selected": False},
            {"Game ID": 3, "Away Team": "Hawks", "Home Team": "Lions",
             "Predicted Winner": "Lions", "Confidence": .62, "Status": "Awaiting final",
             "Live Score": "—", "Pick Result": "Pending", "Value Selected": False},
        ])

    def sample_schedule(self):
        return pd.DataFrame([
            {"game_id": 1, "start_date": "2026-10-10T17:00:00Z"},
            {"game_id": 2, "start_date": "2026-10-10T20:00:00Z"},
            {"game_id": 3, "start_date": "2026-10-11T00:00:00Z"},
        ])

    def test_live_before_upcoming_and_final(self):
        rows = live_board_rows(self.sample_predictions(), self.sample_schedule())
        self.assertEqual([r["section"] for r in rows], ["Live", "Upcoming", "Final"])
        self.assertEqual(rows[0]["winner"], "Tigers")
        self.assertEqual(rows[0]["score"], "Wolves 14 – Tigers 17")
        self.assertEqual(rows[1]["score"], "")
        self.assertEqual(rows[2]["score"], "Owls 10 – Bears 21")

    def test_date_time_and_original_pregame_estimate(self):
        rows = live_board_rows(self.sample_predictions(), self.sample_schedule())
        self.assertEqual(rows[0]["kickoff"], "Sat, Oct 10 · 3:00 PM CT")
        self.assertEqual(rows[0]["chance"], "81.0%")
        self.assertEqual(rows[1]["kickoff"], "Sat, Oct 10 · 7:00 PM CT")

    def test_empty_slates_and_missing_schedules(self):
        empty = self.sample_predictions().iloc[:0]
        self.assertEqual(live_board_rows(empty, self.sample_schedule()), [])
        self.assertEqual(live_board_html([]), "")
        no_dates = live_board_rows(self.sample_predictions(), pd.DataFrame())
        self.assertTrue(all(r["kickoff"] == "Kickoff TBD" for r in no_dates))

    def test_missing_live_score_does_not_invent_points(self):
        frame = self.sample_predictions()
        frame.loc[1, "Live Score"] = "—"
        row = live_board_rows(frame, self.sample_schedule())[0]
        self.assertEqual(row["score"], "")
        html = live_board_html([row])
        self.assertIn("Score unavailable", html)
        self.assertNotIn("Wolves 14", html)

    def test_unsafe_team_and_feed_strings_are_escaped(self):
        frame = self.sample_predictions()
        frame.loc[1, "Home Team"] = "<script>x</script>"
        frame.loc[1, "Live Detail"] = "<img src=x onerror=x>"
        html = live_board_html(live_board_rows(frame, self.sample_schedule()))
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;img", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img src=x", html)

    def test_value_tier_and_final_result_labels_only_when_applicable(self):
        html = live_board_html(live_board_rows(self.sample_predictions(), self.sample_schedule()))
        self.assertIn("Tier 1: Complete Game", html)
        self.assertIn("Correct pick", html)
        self.assertEqual(html.count("Correct pick"), 1)
        self.assertIn("Pregame model pick", html)

    def test_final_pending_score_not_graded(self):
        frame = self.sample_predictions().copy()
        frame.loc[0, "Status"] = "Final · score pending"
        frame.loc[0, "Final Score"] = "—"
        frame.loc[0, "Pick Result"] = "Pending"
        result = live_board_rows(frame, self.sample_schedule())
        self.assertEqual(result[-1]["section"], "Final")
        self.assertEqual(result[-1]["score"], "")
        self.assertNotIn("Correct pick", live_board_html(result))

    def test_known_sections_are_stable(self):
        self.assertEqual(LIVE_SECTIONS, ("Live", "Upcoming", "Final"))


if __name__ == "__main__":
    unittest.main()
