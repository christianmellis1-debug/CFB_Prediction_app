"""ATS grading regression: home/away orientation, pushes, split edges."""
import unittest
import numpy as np
import pandas as pd
from research.handwritten_offense_defense_2026_10_12.home_field_ats import (
    grade,cohort_breakdown
)


class HomeATSResearchTests(unittest.TestCase):
    def test_home_spread_and_pushes(self):
        # margin = home score - away score + home_team_spread.
        margins=np.array([7-3.5, 3-3.5, 3-3.0, -3+6.5])
        ats=np.where(margins>1e-8,1,np.where(margins< -1e-8,-1,0))
        np.testing.assert_array_equal(ats,[1,-1,0,1])
        mask=np.ones(4,dtype=bool)
        home=grade(mask,np.ones(4,int),ats)
        self.assertEqual(home,{"qualified":4,"wins":2,"losses":1,"pushes":1,
                              "decisions":3,"ats_win_pct":0.666667})
        away=grade(mask,-np.ones(4,int),ats)
        self.assertEqual(away["wins"],1)
        self.assertEqual(away["losses"],2)
        self.assertEqual(away["pushes"],1)

    def test_qualifier_home_away_and_neutral_distinct(self):
        data=pd.DataFrame([
          {"neutral_site":False,"off_side":1,"def_side":1,"both_side":1,
           "v15_side":1,"handwritten_side":1,"ats_home_result":1,
           "odds_source":"summary_pickcenter"},
          {"neutral_site":False,"off_side":-1,"def_side":-1,"both_side":-1,
           "v15_side":1,"handwritten_side":-1,"ats_home_result":-1,
           "odds_source":"core_odds_api"},
          {"neutral_site":False,"off_side":1,"def_side":1,"both_side":1,
           "v15_side":-1,"handwritten_side":-1,"ats_home_result":0,
           "odds_source":"summary_pickcenter"},
          {"neutral_site":True,"off_side":1,"def_side":1,"both_side":1,
           "v15_side":1,"handwritten_side":1,"ats_home_result":-1,
           "odds_source":"summary_pickcenter"},
          {"neutral_site":False,"off_side":1,"def_side":-1,"both_side":0,
           "v15_side":-1,"handwritten_side":-1,"ats_home_result":1,
           "odds_source":"core_odds_api"},
        ])
        result=cohort_breakdown(data)
        self.assertEqual(result["matched_games"],5)
        self.assertEqual(result["home_team_both_edges"]["qualified"],2)
        self.assertEqual(result["home_team_both_edges"]["pushes"],1)
        self.assertEqual(result["home_team_both_edges"]["wins"],1)
        self.assertEqual(result["away_team_both_edges"]["wins"],1)
        self.assertEqual(result["both_edges_neutral"]["losses"],1)
        self.assertEqual(result["both_edges_vs_original_v15"]["conflict_with_v15_original"]["qualified"],2)
        self.assertEqual(result["split_edges"]["higher_offense"]["wins"],1)
        self.assertEqual(result["split_edges"]["higher_defense"]["losses"],1)


if __name__=="__main__":
    unittest.main()
