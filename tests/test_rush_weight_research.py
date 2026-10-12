"""Regression checks for rush offense/defense independent coefficient tests."""
import unittest
import numpy as np
import pandas as pd

from research.run_offense_defense_2026_10_12.run import (
    BASE, FORMULAS, PLANS, valid_rush_box, rush_zscores, probabilities
)


class RushWeightResearch(unittest.TestCase):
    def test_prespecified_families(self):
        self.assertEqual(len(PLANS), len(set(n for n, _, _ in PLANS)))
        for label, weights in FORMULAS.items():
            self.assertAlmostEqual(sum(weights), 1)
            if label.startswith(("epa_", "success_")):
                self.assertEqual(weights[1 if label.startswith("epa_") else 0], 0)
        self.assertAlmostEqual(sum(BASE), 1)

    def test_rushing_and_defense_are_independent(self):
        # Home gains 7 YPC versus the opponent's 3 YPC; home also
        # allows 3 YPC versus away's 7, so the rush-defense sign flips.
        boxes = pd.DataFrame([
            {"game_id": 100, "team_id": 1, "rushingYards": 140, "rushingAttempts": 20},
            {"game_id": 100, "team_id": 2, "rushingYards": 60, "rushingAttempts": 20},
            {"game_id": 101, "team_id": 3, "rushingYards": 90, "rushingAttempts": 20},
            {"game_id": 101, "team_id": 4, "rushingYards": 110, "rushingAttempts": 20},
            {"game_id": 102, "team_id": 1, "rushingYards": 60, "rushingAttempts": 20},
            {"game_id": 102, "team_id": 3, "rushingYards": 160, "rushingAttempts": 20},
        ])
        games = pd.DataFrame([
            {"game_id": 100, "home_id": 1, "away_id": 2},
            {"game_id": 101, "home_id": 3, "away_id": 4},
            {"game_id": 102, "home_id": 1, "away_id": 3},
        ])
        z, report = rush_zscores(games, valid_rush_box(boxes))
        self.assertEqual(report["complete_past_games"], 3)
        self.assertGreater(z[1][0], z[2][0])
        self.assertGreater(z[1][1], z[2][1])
        self.assertNotEqual(z[1][0], z[1][1])

    def test_ambiguous_box_does_not_enter_past_profile(self):
        b = pd.DataFrame([
            {"game_id": 100, "team_id": 1, "rushingYards": 100, "rushingAttempts": 20},
            {"game_id": 100, "team_id": 1, "rushingYards": 200, "rushingAttempts": 20},
            {"game_id": 100, "team_id": 2, "rushingYards": 120, "rushingAttempts": 20},
        ])
        games = pd.DataFrame([{"game_id": 100, "home_id": 1, "away_id": 2}])
        z, quality = rush_zscores(games, valid_rush_box(b))
        self.assertEqual(z,{})
        self.assertEqual(quality["missing_box_games"], 1)

    def test_baseline_probabilities_remain_identical(self):
        frame = pd.DataFrame([{
            "base_p":0.65,"current_weight":0.7,
            **{"o_"+key:0 for key in FORMULAS},
            **{"d_"+key:0 for key in FORMULAS},
        }])
        prob = probabilities(frame,"current_no_rush","current_no_rush")
        self.assertAlmostEqual(prob[0],0.65,places=12)


if __name__=="__main__":
    unittest.main()
