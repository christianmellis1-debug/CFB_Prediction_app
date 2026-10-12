"""Protect handwritten offense/defense weights, pregame box validation and grade."""
import unittest
import numpy as np
import pandas as pd
from research.handwritten_offense_defense_2026_10_12.run import (
    WEIGHTS, BASE, prepare_full_boxes, standardized_team_profiles, report
)


def sample_boxes():
    games=[]
    for game_id,home,away,hy,ay,hcomp,acomp,hto,ato in [
        (10,1,2,120,80,13,9,1,2),
        (11,3,4,70,110,10,14,2,1),
        (12,1,3,95,125,12,13,0,3),
    ]:
        for tid,y,c,to in [(home,hy,hcomp,hto),(away,ay,acomp,ato)]:
            games.append(dict(
                game_id=game_id,team_id=tid,rushingYards=y,rushingAttempts=20,
                completionAttempts=f"{c}-20",turnovers=to,
                fumblesLost=0,interceptions=to))
    return pd.DataFrame(games)


class HandwrittenFormulaTests(unittest.TestCase):
    def test_exact_handwritten_weights(self):
        self.assertEqual(WEIGHTS,{
            "epa":.40,"run":.25,"pass":.15,"turnovers":.10,"explosive":.10
        })
        self.assertAlmostEqual(sum(WEIGHTS.values()),1)
        self.assertAlmostEqual(sum(BASE.values()),1)
        self.assertNotIn("success",WEIGHTS)
        self.assertNotIn("red_zone",WEIGHTS)

    def test_box_scores_and_signed_run_pass_defense(self):
        history=pd.DataFrame([
            {"game_id":10,"home_id":1,"away_id":2},
            {"game_id":11,"home_id":3,"away_id":4},
            {"game_id":12,"home_id":1,"away_id":3},
        ])
        z,report_quality=standardized_team_profiles(history,
                                                      prepare_full_boxes(sample_boxes()))
        self.assertEqual(report_quality["accepted_complete_games"],3)
        self.assertEqual(report_quality["teams_with_valid_full_history"],4)
        # Team 1 produces a higher YPC than team 2.
        self.assertGreater(z[1][0],z[2][0])
        # Team 1 allows fewer opponent YPC and completions than team 2.
        self.assertGreater(z[1][3],z[2][3])
        self.assertGreater(z[1][4],z[2][4])
        # More giveaways must be negative for offensive rating.
        self.assertGreater(z[1][2],z[3][2])

    def test_invalid_or_missing_history_fails_closed(self):
        history=pd.DataFrame([
            {"game_id":10,"home_id":1,"away_id":2},
            {"game_id":11,"home_id":3,"away_id":4},
            {"game_id":12,"home_id":1,"away_id":3},
        ])
        all_box=sample_boxes()
        incomplete=all_box[~(
            (all_box.game_id==12)&(all_box.team_id==3)
        )]
        profiles,quality=standardized_team_profiles(
            history,prepare_full_boxes(incomplete))
        self.assertNotIn(1,profiles)
        self.assertNotIn(3,profiles)
        self.assertEqual(quality["incomplete_box_games"],1)
        self.assertIn(2,profiles)
        self.assertIn(4,profiles)

    def test_refuse_turnover_inconsistency_and_bad_pass_attempts(self):
        bad=sample_boxes()
        bad.loc[(bad.game_id==10)&(bad.team_id==1),"turnovers"]=5
        bad.loc[(bad.game_id==11)&(bad.team_id==3),"completionAttempts"]="24-20"
        x=prepare_full_boxes(bad)
        self.assertNotIn((10,1),x.index)
        self.assertNotIn((11,3),x.index)

    def test_grades_same_games_and_probability_quality(self):
        frame=pd.DataFrame([
            {"home_win":1,"baseline_probability":.7,"custom_probability":.8},
            {"home_win":0,"baseline_probability":.6,"custom_probability":.4},
            {"home_win":1,"baseline_probability":.4,"custom_probability":.7},
        ])
        base=report(frame,"baseline_probability")
        custom=report(frame,"custom_probability")
        self.assertEqual(base["games"],custom["games"])
        self.assertEqual(base["wins"],1)
        self.assertEqual(custom["wins"],3)
        self.assertLess(custom["brier"],base["brier"])


if __name__=="__main__":
    unittest.main()
