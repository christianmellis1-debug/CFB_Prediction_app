"""Research regression guards for written formula plus independent home field."""
import unittest
import numpy as np
import pandas as pd
from research.handwritten_offense_defense_2026_10_12.home_field import (
    conditional_records, grade_probability, new_probability, PRODUCTION_VENUE_COEFFICIENT
)


class HandwrittenHomeFieldTests(unittest.TestCase):
    def games(self):
        return pd.DataFrame([
          {"home_win":1, "proposed_offense_edge":.5, "proposed_defense_edge":.3,
           "baseline_probability":.6,"custom_probability":.64,"venue_signal":.35,
           "neutral_site":False},
          {"home_win":0, "proposed_offense_edge":-.5, "proposed_defense_edge":-.3,
           "baseline_probability":.4,"custom_probability":.35,"venue_signal":-.25,
           "neutral_site":False},
          {"home_win":1, "proposed_offense_edge":-.5, "proposed_defense_edge":-.3,
           "baseline_probability":.49,"custom_probability":.48,"venue_signal":0.,
           "neutral_site":True},
          {"home_win":0, "proposed_offense_edge":.3, "proposed_defense_edge":-.4,
           "baseline_probability":.41,"custom_probability":.43,"venue_signal":-.1,
           "neutral_site":False},
        ])

    def test_home_away_neutral_conditions(self):
        x=conditional_records(self.games())
        self.assertEqual(x["all_games"],4)
        self.assertEqual(x["non_neutral_games"],3)
        self.assertEqual(x["neutral_site_games"],1)
        self.assertEqual(x["both_advantages_home_non_neutral"]["games"],1)
        self.assertEqual(x["both_advantages_home_non_neutral"]["wins"],1)
        self.assertEqual(x["both_advantages_away_non_neutral"]["games"],1)
        self.assertEqual(x["both_advantages_away_non_neutral"]["wins"],1)
        self.assertEqual(x["both_advantages_neutral"]["games"],1)
        self.assertEqual(x["both_advantages_neutral"]["wins"],0)
        self.assertEqual(x["split_advantages_non_neutral_home_team"]["games"],1)

    def test_existing_20pct_is_exact_baseline(self):
        games=self.games()
        new=new_probability(games,venue_weight=PRODUCTION_VENUE_COEFFICIENT)
        np.testing.assert_allclose(new,games.custom_probability.to_numpy(),atol=1e-13)
        same=new_probability(games,venue_weight=.20,home_bonus=0.)
        np.testing.assert_allclose(same,new,atol=1e-13)

    def test_neutral_field_never_affected_by_home_adjustment(self):
        games=self.games()
        original=games.custom_probability.to_numpy()
        no_venue=new_probability(games,venue_weight=0.)
        more_venue=new_probability(games,venue_weight=.40)
        bonus=new_probability(games,venue_weight=.20,home_bonus=.20)
        self.assertAlmostEqual(no_venue[2],original[2],places=12)
        self.assertAlmostEqual(more_venue[2],original[2],places=12)
        self.assertAlmostEqual(bonus[2],original[2],places=12)
        self.assertGreater(more_venue[0],original[0])
        self.assertLess(no_venue[0],original[0])
        self.assertGreater(bonus[0],original[0])

    def test_all_variants_use_same_games(self):
        data=self.games()
        a=grade_probability(data,data.custom_probability.to_numpy())
        b=grade_probability(data,new_probability(data,venue_weight=.40))
        self.assertEqual(a["games"],4)
        self.assertEqual(b["games"],4)
        self.assertAlmostEqual(a["accuracy"],round(a["wins"]/4,6))


if __name__=="__main__":
    unittest.main()
