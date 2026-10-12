"""Verify mutually exclusive both/split categories and matched games."""
import unittest
import pandas as pd
from research.handwritten_offense_defense_2026_10_12.unit_advantages import summarize


class UnitAdvantageTests(unittest.TestCase):
    def test_both_and_split_counts(self):
        games=pd.DataFrame([
            # same home team better at both, home wins
            {"home_win":1,"proposed_offense_edge":.5,"proposed_defense_edge":.3},
            # same away team better at both, away wins
            {"home_win":0,"proposed_offense_edge":-.4,"proposed_defense_edge":-.2},
            # home offense better, away defense better, away wins
            {"home_win":0,"proposed_offense_edge":.4,"proposed_defense_edge":-.5},
            # away offense better, home defense better, home wins
            {"home_win":1,"proposed_offense_edge":-.3,"proposed_defense_edge":.2},
            # home offense, defense tied
            {"home_win":1,"proposed_offense_edge":.3,"proposed_defense_edge":0.0},
            # both tied
            {"home_win":0,"proposed_offense_edge":0.0,"proposed_defense_edge":0.0}
        ])
        result=summarize(games)
        self.assertEqual(result["total_games"],6)
        self.assertEqual(result["higher_offense"]["games"],5)
        self.assertEqual(result["higher_offense"]["wins"],3)
        self.assertEqual(result["higher_defense"]["games"],4)
        self.assertEqual(result["higher_defense"]["wins"],4)
        self.assertEqual(result["same_team_better_at_both"],{
            "games":2,"wins":2,"losses":0,"win_rate":1.0
        })
        split=result["different_teams_split_the_edges"]
        self.assertEqual(split["games"],2)
        self.assertEqual(split["better_offense"]["wins"],0)
        self.assertEqual(split["better_defense"]["wins"],2)
        self.assertEqual(result["one_metric_tied_games"],1)
        self.assertEqual(result["both_metrics_tied_games"],1)

    def test_separates_original_from_custom(self):
        df=pd.DataFrame([
            {"home_win":1,
             "proposed_offense_edge":.5,"proposed_defense_edge":.5,
             "original_offense_edge":-.5,"original_defense_edge":-.5}
        ])
        custom=summarize(df)
        original=summarize(df,"original_offense_edge","original_defense_edge")
        self.assertEqual(custom["same_team_better_at_both"]["wins"],1)
        self.assertEqual(original["same_team_better_at_both"]["wins"],0)

    def test_missing_scores_not_reported_as_losses(self):
        df=pd.DataFrame([
            {"home_win":1,"proposed_offense_edge":float("nan"),
             "proposed_defense_edge":1.0}
        ])
        with self.assertRaises(ValueError):
            summarize(df)


if __name__=="__main__":
    unittest.main()
