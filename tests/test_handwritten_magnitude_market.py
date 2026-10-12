"""Verify no overlapping category leakage or unfair favorite comparison."""
import unittest
import pandas as pd
from research.handwritten_offense_defense_2026_10_12.magnitude_market import (
    magnitude_groups,separate_unit_magnitudes,market_favorites_comparison,spread_bucket
)

def row(season,off,defense,win,spread,neutral=False):
    return dict(season=season,proposed_offense_edge=off,
                proposed_defense_edge=defense,home_win=win,
                home_team_spread=spread,neutral_site=neutral,
                min_advantage=min(off,defense))


class MagnitudeMarketTest(unittest.TestCase):
    def test_disjoint_magnitudes(self):
        d=pd.DataFrame([
            row(2026,.10,.9,1,-3),
            row(2026,.30,.7,0,-10),
            row(2026,.55,.8,1,-14),
            row(2026,1.15,1.7,1,-24),
            row(2026,1.9,1.6,0,-27),
            row(2026,2,.3,1,5),
            row(2026,1,.8,1,-7,True),
            row(2026,-.3,.7,0,-7),
        ])
        result=magnitude_groups(d)
        self.assertEqual(result["total"]["games"],6)
        self.assertEqual(result["total"]["wins"],4)
        self.assertEqual(result["nonoverlapping_bins"]["0–0.25"]["games"],1)
        self.assertEqual(result["nonoverlapping_bins"]["0.25–0.5"]["games"],2)
        self.assertEqual(result["nonoverlapping_bins"]["0.5–0.75"]["games"],1)
        self.assertEqual(result["nonoverlapping_bins"]["1–1.5"]["games"],1)
        self.assertEqual(result["nonoverlapping_bins"]["1.5+"]["games"],1)
        self.assertEqual(result["cumulative_minimum_thresholds"]["0.5"]["games"],3)

    def test_independent_offensive_vs_defensive_gap_size(self):
        d=pd.DataFrame([
            row(2026,.2,.2,0,-5),
            row(2026,.7,.2,1,-10),
            row(2026,.2,.7,0,-10),
            row(2026,.7,.7,1,-20),
            row(2026,-.2,.6,1,-7),
        ])
        observed=separate_unit_magnitudes(d)
        self.assertEqual(observed["comparison_population"],4)
        bins=observed["two_by_two"]
        self.assertEqual(bins["both_below_threshold"]["games"],1)
        self.assertEqual(bins["only_offense_at_least_threshold"]["wins"],1)
        self.assertEqual(bins["only_defense_at_least_threshold"]["wins"],0)
        self.assertEqual(bins["both_at_least_threshold"]["wins"],1)

    def test_market_comparison_only_common_support_strata(self):
        d=pd.DataFrame([
            row(2026,.4,.5,1,-9),   # both selected
            row(2026,.6,.3,0,-8),   # both selected
            row(2026,.6,-.2,1,-10), # comparison, 1-0
            row(2026,-.1,.6,0,-12), # comparison, 0-1
            row(2026,.8,.9,1,-30),  # only both, no 21+ control
            row(2025,.3,.4,1,-10),  # earlier year no same-year control
            row(2026,-.4,.2,1,4),   # underdog not a market favorite
        ])
        result=market_favorites_comparison(d)
        self.assertEqual(result["both_home_favorite"]["games"],4)
        matched=result["stratified_comparison"]
        self.assertEqual(matched["matched_by_year_and_spread_bucket_games"],2)
        self.assertEqual(matched["both_games_with_no_spread_stratum_controls"],2)
        self.assertEqual(matched["selected_both_win_rate"],.5)
        self.assertEqual(matched["comparator_weighted_win_rate"],.5)
        self.assertEqual(matched["difference_percentage_points"],0.)
        self.assertEqual(spread_bucket(-20),"14–20.5 point favorite")
        self.assertEqual(spread_bucket(-21),"21+ point favorite")
        self.assertEqual(spread_bucket(-6.5),"Under 7 point favorite")
        self.assertEqual(spread_bucket(4),"not_home_favorite")


if __name__=="__main__":
    unittest.main()
