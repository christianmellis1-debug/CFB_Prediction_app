import unittest
import pandas as pd
from rushing_matchup import (
    build_rushing_matchup_insights, rushing_matchup_html
)


class PregameRushingMismatchTests(unittest.TestCase):
    def setUp(self):
        self.schedule=[]
        self.boxes=[]
        # 16 FBS teams, eight completed week-one matchups, all pregame.
        for i in range(0,16,2):
            h=i+1;a=i+2; gid=100+i
            self.schedule.append(self.game(gid,1,h,a,True,'2026-09-01T16:00:00Z'))
            # Team 1 and team 3 have 1 YPC; all others have 5.
            # Team 2 faces team 3, so its defense allows only 1 YPC.
            # Team 1 is in an earlier game versus team 2; to achieve
            # the desired noncorrelated test profile later, revise pairs.
            for tid in (h,a):
                y=1 if tid in (1,3) else 5
                self.boxes.append(dict(game_id=gid,team_id=tid,
                    rushingYards=20*y,rushingAttempts=20))
        # Team 2's opponent in the first fixture was Team 1 (1 YPC).
        self.schedule.append(self.game(999,2,1,2,False,'2026-09-08T16:00:00Z'))
        self.schedule=pd.DataFrame(self.schedule)
        self.boxes=pd.DataFrame(self.boxes)

    def game(self,gid,w,h,a,done,start):
        return dict(season=2026,season_type='regular',home_division='fbs',
            away_division='fbs',home_conference='SEC',away_conference='SEC',
            home_team=f"Team {h}",away_team=f"Team {a}",
            game_id=gid,week=w,home_id=h,away_id=a,completed=done,
            home_points=14 if done else None,
            away_points=7 if done else None,start_date=start)

    def test_detects_true_weak_run_offense_vs_strong_run_defense(self):
        rec=build_rushing_matchup_insights(self.schedule,self.boxes,2)['999']
        self.assertEqual(rec["status"],"ok")
        self.assertTrue(rec["home_disadvantaged"])
        self.assertFalse(rec["away_disadvantaged"])
        self.assertEqual(rec["peers"],16)
        self.assertAlmostEqual(rec["home"]["off_ypc"],1.)
        self.assertAlmostEqual(rec["away"]["allowed_ypc"],1.)
        self.assertEqual(rec["home"]["prior_games"],1)
        html=rushing_matchup_html(rec,'<Home>','<Away>')
        self.assertIn('&lt;Home&gt;',html)
        self.assertIn('&lt;Away&gt;',html)
        self.assertIn('weak run attack vs strong run defense',html)
        self.assertIn('not an automatic reduction',html)

    def test_only_previous_week_data(self):
        self.boxes=pd.concat([self.boxes,pd.DataFrame([
            dict(game_id=999,team_id=1,rushingYards=10000,rushingAttempts=20),
            dict(game_id=999,team_id=2,rushingYards=0,rushingAttempts=20)])],ignore_index=True)
        rec=build_rushing_matchup_insights(self.schedule,self.boxes,2)['999']
        self.assertTrue(rec["home_disadvantaged"])
        self.assertAlmostEqual(rec["home"]["off_ypc"],1.)
        self.assertAlmostEqual(rec["away"]["allowed_ypc"],1.)
        self.assertEqual(build_rushing_matchup_insights(self.schedule,self.boxes,1).get('999'),None)

    def test_no_flag_when_away_history_missing(self):
        b=self.boxes[self.boxes.team_id.ne(2)]
        rec=build_rushing_matchup_insights(self.schedule,b,2)['999']
        self.assertEqual(rec["status"],"unavailable")
        self.assertEqual(rushing_matchup_html(rec,'Home','Away'),'')

    def test_no_flag_if_peer_population_too_small(self):
        s=self.schedule[self.schedule.home_id.isin([1,3,5])]
        b=self.boxes[self.boxes.game_id.isin(s.game_id)]
        self.assertEqual(build_rushing_matchup_insights(s,b,2).get('999',{}).get("status"),"unavailable")

    def test_duplicate_box_scores_fail_closed(self):
        b=pd.concat([self.boxes,self.boxes.iloc[:1]],ignore_index=True)
        rec=build_rushing_matchup_insights(self.schedule,b,2)['999']
        self.assertEqual(rec["status"],"unavailable")


if __name__=='__main__':
    unittest.main()
