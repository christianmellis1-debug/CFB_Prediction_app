import unittest
import pandas as pd
from research.handwritten_offense_defense_2026_10_12.same_group import group, block

class SameGroupMatchups(unittest.TestCase):
    def test_season_aware_conference_policy(self):
        self.assertEqual(group("Independent","Notre Dame",2022),"P4")
        self.assertEqual(group("ACC","Clemson",2026),"P4")
        self.assertEqual(group("American Athletic","Tulane",2026),"G6")
        self.assertEqual(group("Pac-12","Oregon",2022),"P4")
        self.assertEqual(group("Pac-12","Washington State",2023),"P4")
        self.assertIsNone(group("Pac-12","Oregon State",2024))
        self.assertIsNone(group("Pac-12","Oregon State",2025))
        self.assertEqual(group("Pac-12","Washington State",2026),"G6")
        self.assertIsNone(group("Independent","Unknown",2026))
        self.assertIsNone(group("","Missing",2026))
    def test_filter_p4_v_g6(self):
        cases=[
           dict(home_group="P4",away_group="P4",same_group=True,
                group_pair="P4 vs P4",home_both=True,min_edge=.27,home_win=1),
           dict(home_group="G6",away_group="G6",same_group=True,
                group_pair="G6 vs G6",home_both=True,min_edge=.62,home_win=0),
           dict(home_group="P4",away_group="G6",same_group=False,
                group_pair="P4 vs G6",home_both=True,min_edge=1.4,home_win=1),
           dict(home_group="G6",away_group="P4",same_group=False,
                group_pair="G6 vs P4",home_both=True,min_edge=.05,home_win=1),
           dict(home_group="P4",away_group="P4",same_group=True,
                group_pair="P4 vs P4",home_both=False,min_edge=-.4,home_win=0),
        ]
        report=block(pd.DataFrame(cases))
        self.assertEqual(report["same_group_home_both"]["games"],2)
        self.assertEqual(report["same_group_p4_v_p4"]["wins"],1)
        self.assertEqual(report["same_group_g6_v_g6"]["losses"],1)
        self.assertEqual(report["excluded_home_both_mixed_or_unclassified"]["games"],2)
        self.assertEqual(report["bands_same_group_all"]["0.25–0.5"]["games"],1)
        self.assertEqual(report["bands_same_group_all"]["0.5–0.75"]["games"],1)

if __name__=="__main__":
    unittest.main()
