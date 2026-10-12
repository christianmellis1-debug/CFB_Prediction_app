import unittest
import pandas as pd
from research.handwritten_offense_defense_2026_10_12.favorites_two_tests import stats,summary

class StrictSpreadAB(unittest.TestCase):
    def test_spread_cutoff_and_midrange_removal(self):
        df=pd.DataFrame([
            dict(A=True,B=True,A_heavy=False,home_win=1,home_team_spread=-9.5,home_group="P4",min_magnitude=.3),
            dict(A=True,B=False,A_heavy=True,home_win=0,home_team_spread=-10,home_group="G6",min_magnitude=.8),
            dict(A=True,B=False,A_heavy=True,home_win=1,home_team_spread=-11,home_group="G6",min_magnitude=.6),
            dict(A=False,B=False,A_heavy=False,home_win=1,home_team_spread=+2.5,home_group="P4",min_magnitude=.3),
        ])
        df["rule_without_odds"]=True
        df["has_verified_spread"]=True
        r=summary(df)
        self.assertEqual(r["A"]["games"],3)
        self.assertEqual(r["A"]["wins"],2)
        self.assertEqual(r["B"]["games"],1)
        self.assertEqual(r["B"]["wins"],1)
        self.assertEqual(r["A_heavy"]["games"],2)
        self.assertEqual(r["home_underdogs_or_pickem_in_qualifying_games"],1)
    def test_stats_empty(self):
        df=pd.DataFrame({"home_win":pd.Series(dtype=int),"home_team_spread":pd.Series(dtype=float)})
        r=stats(df)
        self.assertEqual(r["games"],0)
        self.assertIsNone(r["win_pct"])

if __name__=="__main__":
    unittest.main()
