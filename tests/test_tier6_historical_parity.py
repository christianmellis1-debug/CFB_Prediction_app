"""Online replay of 2026 Weeks 3–6 against immutable historical study edges.

This test uses independent 2026 season feed downloads, no completed target
game stats, and checks exact offense/defense edges from the research dataset.
Run separately from the fast offline regression tests.
"""
import csv
import unittest
from pathlib import Path

from home_field_advantage_tier6 import build_tier6_checks
from shadow_inputs import download_schedule, read_summary
from capture_value import boxes


REF=Path("tests/fixtures/home_field_advantage_tier6_2026.csv")


class HistoricalParityTests(unittest.TestCase):
    def test_all_same_group_home_both_rating_edges_2026(self):
        with REF.open() as file:
            expected=[row for row in csv.DictReader(file) if row["same_group"]=="True"]
        self.assertEqual(len(expected),59)
        schedule=download_schedule(2026)
        current=read_summary(None,2026)
        previous=read_summary(None,2025)
        box=boxes(2026)
        compared=0
        for week in (3,4,5,6):
            checks=build_tier6_checks(schedule,box,current,previous,week)
            for case in [x for x in expected if int(x["week"])==week]:
                rec=checks.get(case["game_id"])
                self.assertIsNotNone(rec,case)
                self.assertEqual(rec["status"],"ok",case)
                self.assertAlmostEqual(rec["off_edge"],float(case["off_edge"]),delta=1e-8,msg=str(case))
                self.assertAlmostEqual(rec["def_edge"],float(case["def_edge"]),delta=1e-8,msg=str(case))
                self.assertAlmostEqual(rec["magnitude"],float(case["min_edge"]),delta=1e-8,msg=str(case))
                if rec["group"]=="P4" and .5<=rec["magnitude"]<.75:
                    self.assertFalse(rec["qualifies"])
                else:
                    self.assertTrue(rec["qualifies"])
                compared+=1
        self.assertEqual(compared,59)


if __name__=="__main__":
    unittest.main()
