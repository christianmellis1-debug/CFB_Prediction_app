import unittest
import pandas as pd
from matchup_advantages import build_advantages,assess,advantage_html
class AdvantageTests(unittest.TestCase):
 def setUp(self):
  common=dict(season=2026,season_type='regular',home_division='fbs',away_division='fbs',home_conference='SEC',away_conference='SEC',home_points=21,away_points=10,completed=True)
  self.s=pd.DataFrame([dict(common,game_id=1,week=1,home_id=10,away_id=20,start_date='2026-09-01T00:00:00Z'),dict(common,game_id=2,week=2,home_id=10,away_id=20,start_date='2026-09-08T00:00:00Z',completed=False)])
  self.b=pd.DataFrame([dict(game_id=1,team_id=10,rushingYards=200,rushingAttempts=40,completionAttempts='20/30',turnovers=0,fumblesLost=0,interceptions=0),dict(game_id=1,team_id=20,rushingYards=100,rushingAttempts=40,completionAttempts='10/30',turnovers=2,fumblesLost=1,interceptions=1)])
 def test_opposite_sides(self):
  r=build_advantages(self.s,self.b,2)['2']
  self.assertEqual(assess(r,'home')['count'],5);self.assertEqual(assess(r,'away')['count'],0)
  self.assertIn('Matchup risk',advantage_html(r,'away','<Away>'))
  self.assertNotIn('Matchup risk',advantage_html(r,'home','Home'))
  self.assertIn('&lt;Away&gt;',advantage_html(r,'away','<Away>'))
 def test_missing_is_not_zero(self):
  r=build_advantages(self.s,self.b.iloc[:1],2)['2']
  self.assertIsNone(assess(r,'home'));self.assertNotIn('Matchup risk',advantage_html(r,'home','Home'))
 def test_no_same_week_leakage(self):
  r=build_advantages(self.s,self.b,1)['1'];self.assertEqual(r['status'],'missing')
 def test_scope(self):
  self.s.loc[1,'away_conference']='Sun Belt'
  self.assertEqual(build_advantages(self.s,self.b,2)['2']['status'],'outside')
 def test_ties_and_threshold(self):
  r=dict(status='ok',home=[5,.6,4,.5,0],away=[5,.6,4,.5,0])
  self.assertEqual(assess(r,'home')['count'],0)
  r['home'][0]=6;self.assertTrue(assess(r,'home')['flag'])
  r['home'][1]=.7;self.assertTrue(assess(r,'home')['flag'])
  r['home'][4]=1;self.assertFalse(assess(r,'home')['flag'])
 def test_notre_dame_is_p4_on_either_side(self):
  for side in ('home','away'):
   with self.subTest(side=side):
    s=self.s.copy()
    s.loc[1,side+'_conference']='FBS Independents'
    s.loc[1,side+'_team']='Notre Dame'
    r=build_advantages(s,self.b,2)['2']
    self.assertEqual(r['status'],'ok');self.assertEqual(r['group'],'P4')
    s.loc[1,('away' if side=='home' else 'home')+'_conference']='Sun Belt'
    self.assertEqual(build_advantages(s,self.b,2)['2']['status'],'outside')
    s.loc[1,side+'_team']='UConn'
    self.assertEqual(build_advantages(s,self.b,2)['2']['status'],'outside')
 def test_turnover_direction_and_zero_giveaways(self):
  r=build_advantages(self.s,self.b,2)['2']
  self.assertEqual(r['home'][4],2);self.assertEqual(r['away'][4],-2)
  self.assertEqual(assess(r,'home')['outcomes'][4],'Advantage')
  self.assertIn('+2.00 per game',advantage_html(r,'home','Home'))
 def test_invalid_turnovers_not_risk(self):
  for value in (None,-1,1.5,3):
   b=self.b.copy();b['turnovers']=b['turnovers'].astype(object);b.loc[1,'turnovers']=value
   r=build_advantages(self.s,b,2)['2']
   self.assertEqual(r['status'],'missing');self.assertIsNone(assess(r,'home'))
  r=build_advantages(self.s,self.b.drop(columns=['turnovers']),2)['2']
  self.assertEqual(r['status'],'missing')
if __name__=='__main__':unittest.main()
