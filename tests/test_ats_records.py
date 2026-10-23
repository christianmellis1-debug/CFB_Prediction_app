import pandas as pd
import unittest

from ats_records import (ats_label, calculate_ats_records,
                         calculate_overall_records, overall_ats_label)


def _games():
    return pd.DataFrame([
        # Team 1 loses ATS at home despite winning straight up by four.
        dict(game_id=101, season=2026, week=1, home_id=1, away_id=2,
             home_points=24, away_points=20, completed=True, season_type="regular", fbs_game=True),
        # An exact push for both sides, with team 1 on the road.
        dict(game_id=102, season=2026, week=2, home_id=3, away_id=1,
             home_points=28, away_points=21, completed=True, season_type="regular", fbs_game=True),
        # Played, but market coverage is missing.
        dict(game_id=103, season=2026, week=3, home_id=2, away_id=3,
             home_points=17, away_points=13, completed=True, season_type="regular", fbs_game=True),
        # Never allow selected-week results into pregame ATS information.
        dict(game_id=104, season=2026, week=4, home_id=1, away_id=3,
             home_points=35, away_points=0, completed=True, season_type="regular", fbs_game=True),
        # No in-progress game counts even with scores populated.
        dict(game_id=105, season=2026, week=2, home_id=1, away_id=4,
             home_points=7, away_points=0, completed=False, season_type="regular", fbs_game=True),
        # FCS opponent games must not contribute.
        dict(game_id=106, season=2026, week=2, home_id=1, away_id=5,
             home_points=7, away_points=0, completed=True, season_type="regular", fbs_game=False),
    ])


def _lines():
    return pd.DataFrame([
        dict(game_id=101, home_team_spread=-7.0, game_spread_available=True, odds_source="summary_pickcenter"),
        dict(game_id=102, home_team_spread=-7.0, game_spread_available=True, odds_source="core_odds_api"),
        # A fallback -0 cannot be treated as a real spread.
        dict(game_id=103, home_team_spread=0.0, game_spread_available=False, odds_source="default"),
        dict(game_id=104, home_team_spread=-14.0, game_spread_available=True, odds_source="summary_pickcenter"),
        dict(game_id=105, home_team_spread=10.0, game_spread_available=True, odds_source="summary_pickcenter"),
        dict(game_id=106, home_team_spread=-4.0, game_spread_available=True, odds_source="summary_pickcenter"),
    ])



class TestATSRecords(unittest.TestCase):
    def test_overall_record_includes_fcs_but_not_future_or_incomplete_games(self):
        # Team 1 beat team 2 in Week 1, lost at team 3 in Week 2,
        # beat the FCS opponent in Week 2, then had a scheduled Week 4 win.
        actual = calculate_overall_records(_games(), week=4, season=2026)
        self.assertEqual(actual[1], {"wins": 2, "losses": 1})
        self.assertEqual(actual[2], {"wins": 1, "losses": 1})
        self.assertEqual(actual[3], {"wins": 1, "losses": 1})
        self.assertEqual(actual[5], {"wins": 0, "losses": 1})
        self.assertNotIn(4, actual)

    def test_overall_record_is_not_dependent_on_betting_lines(self):
        actual = calculate_overall_records(_games(), week=4, season=2026)
        ats = calculate_ats_records(_games(), _lines(), 4)
        self.assertEqual(overall_ats_label(actual[1], ats[1]), "W–L 2–1 · ATS 0–1–1")
        self.assertEqual(
            overall_ats_label(actual[1], ats[1], ats_feed_available=False),
            "W–L 2–1 · ATS unavailable",
        )
        self.assertEqual(overall_ats_label(None, None), "W–L 0–0 · ATS 0–0–0")

    def test_overall_records_deduplicate_and_respect_season_and_week(self):
        games = _games()
        copy = games.loc[games.game_id.eq(101)].copy()
        out_of_season = copy.copy()
        out_of_season["season"] = 2025
        out_of_season["game_id"] = 9999
        duplicated = pd.concat([games, copy, out_of_season], ignore_index=True)
        actual = calculate_overall_records(duplicated, 4, 2026)
        self.assertEqual(actual[1], {"wins": 2, "losses": 1})
        self.assertEqual(calculate_overall_records(duplicated, 1, 2026), {})

    def test_overall_records_missing_scores_do_not_count(self):
        games = _games()
        games.loc[games.game_id.eq(106), "away_points"] = None
        records = calculate_overall_records(games, 4, 2026)
        self.assertEqual(records[1], {"wins": 1, "losses": 1})
        self.assertEqual(calculate_overall_records(pd.DataFrame(), 4), {})

    def test_ats_results_are_spread_based_and_pregame(self):
        records = calculate_ats_records(_games(), _lines(), 4)
        assert records[1] == dict(wins=0, losses=1, pushes=1, graded=2, eligible=2)
        assert records[2] == dict(wins=1, losses=0, pushes=0, graded=1, eligible=2)
        assert records[3] == dict(wins=0, losses=0, pushes=1, graded=1, eligible=2)
        assert 4 not in records
        assert 5 not in records
        assert ats_label(records[2]) == "ATS 1–0–0 · 1/2 lined"



    def test_week_boundary_does_not_leak_future_scores(self):
        records = calculate_ats_records(_games(), _lines(), 2)
        assert records[1] == dict(wins=0, losses=1, pushes=0, graded=1, eligible=1)
        assert 3 not in records



    def test_missing_lines_do_not_inflate_ats_record(self):
        records = calculate_ats_records(_games(), pd.DataFrame(), 4)
        assert records[1]["eligible"] == 2
        assert records[1]["graded"] == 0
        assert ats_label(records[1]) == "ATS 0–0–0 · 0/2 lined"
        assert ats_label(records[1], feed_available=False) == "ATS unavailable"



    def test_deduplicated_games_count_once_and_no_default_odds(self):
        g = _games()
        duplicated = pd.concat([g, g[g.game_id.eq(101)]], ignore_index=True)
        lines = _lines().copy()
        lines.loc[lines.game_id.eq(103), "game_spread_available"] = True
        # Even if a provider accidentally marks a hardcoded default as available, exclude it.
        records = calculate_ats_records(duplicated, lines, 4)
        assert records[1]["eligible"] == 2
        assert records[2]["graded"] == 1



    def test_empty_and_bad_market_schema_are_safe(self):
        assert calculate_ats_records(pd.DataFrame(), _lines(), 4) == {}
        result = calculate_ats_records(_games(), pd.DataFrame([{"game_id": 101}]), 4)
        assert result[1]["graded"] == 0

if __name__ == "__main__":
    unittest.main()
