import unittest
import pandas as pd
from matchup_advantages import build_waterfall_profiles, select_waterfall, normalize_fbs_schedule
from model_v1_5 import add_waterfall_value, waterfall_scenario_rows

class WaterfallTests(unittest.TestCase):
    def fixture(self, stage=1, gid=1):
        g = dict(game_id=gid, season=2026, week=3, home_id=10, away_id=20,
                 home_team='Home', away_team='Away', home_division='fbs', away_division='fbs',
                 neutral_site=False, start_date='2026-09-19T12:00:00Z')
        p = {'Game ID':gid, 'DK Home ML':'+120', 'DK Away ML':'-140',
             'Predicted Winner':'Away', 'Confidence':.75}
        rec = {'status':'ok','home':dict(off_run=6,def_run=3,margin=1,games=2),
               'away':dict(off_run=4,def_run=5,margin=0,games=2)}
        if stage > 1:
            p.update({'DK Home ML':'-300' if stage==2 else '-250','DK Away ML':'+220', 'Predicted Winner':'Home'})
        return g,p,rec
    def select(self,g,p,r,**kw):
        return select_waterfall(pd.DataFrame([p]),pd.DataFrame([g]),{str(g['game_id']):r},**kw)
    def test_three_stages(self):
        for stage in (1,2,3):
            g,p,r=self.fixture(stage);card=self.select(g,p,r)
            self.assertEqual(card[0]['Value Stage'],stage)
    def test_road_sweep_and_neutral(self):
        g,p,r=self.fixture();p['DK Home ML'],p['DK Away ML']=p['DK Away ML'],p['DK Home ML'];r['home'],r['away']=r['away'],r['home']
        self.assertIn('Road Sweep',self.select(g,p,r)[0]['Value Reason'])
        g['neutral_site']=True;self.assertEqual(self.select(g,p,r),[])
    def test_boundaries_and_gaps(self):
        for stage,good,bad in [(1,[100,170],[99,171]),(2,[-280,-600],[-279,-601]),(3,[-205,-275],[-204,-276])]:
            for line in good+bad:
                g,p,r=self.fixture(stage);p['DK Home ML']=str(line)
                self.assertEqual(bool(self.select(g,p,r)),line in good,(stage,line))
    def test_ties(self):
        for stage in (1,2,3):
            g,p,r=self.fixture(stage);r['home']['margin']=r['away']['margin']
            self.assertEqual(bool(self.select(g,p,r)),stage==2)
        for stage in (1,2,3):
            g,p,r=self.fixture(stage)
            r['home']['def_run']=r['away']['def_run'] if stage==1 else r['away']['off_run']
            self.assertFalse(self.select(g,p,r))
    def test_model_gate(self):
        for confidence, winner, ok in [(.7,'Home',True),(.699,'Home',False),(.9,'Away',False),(float('nan'),'Home',False),(70,'Home',False)]:
            g,p,r=self.fixture(2);p.update(Confidence=confidence, **{'Predicted Winner':winner})
            self.assertEqual(bool(self.select(g,p,r)),ok)
    def test_missing_fcs_and_fallback_prices(self):
        g,p,r=self.fixture();g['away_division']='fcs';self.assertFalse(self.select(g,p,r))
        g,p,r=self.fixture();p['DK Home ML']='Unavailable';p['Home ML']='+120';self.assertFalse(self.select(g,p,r))
        g,p,r=self.fixture();r['home']['margin']=float('nan');self.assertFalse(self.select(g,p,r))
    def test_waterfall_volume_and_priority(self):
        for sizes,expected in [((20,20,20),(18,0,0)),((13,20,20),(13,0,0)),((4,20,20),(4,8,0)),((4,3,20),(4,3,5)),((1,1,1),(1,1,1))]:
            games=[];pred=[];profiles={};gid=0
            for stage,n in enumerate(sizes,1):
                for _ in range(n):
                    gid+=1;g,p,r=self.fixture(stage,gid);games.append(g);pred.append(p);profiles[str(gid)]=r
            card=select_waterfall(pd.DataFrame(pred[::-1]),pd.DataFrame(games),profiles)
            self.assertEqual(tuple(sum(x['Value Stage']==i for x in card) for i in (1,2,3)),expected)
            self.assertEqual(len({x['Game ID'] for x in card}),len(card))
    def history(self):
        g,_,_=self.fixture();g.update(game_id=3,week=3,completed=False)
        old=dict(g,game_id=1,week=1,start_date='2026-09-01T12:00:00Z',completed=True)
        fcs=dict(old,game_id=2,week=2,away_id=30,away_division='fcs')
        b=pd.DataFrame([dict(game_id=1,team_id=10,rushingYards=240,rushingAttempts=40,turnovers=0,fumblesLost=0,interceptions=0),dict(game_id=1,team_id=20,rushingYards=120,rushingAttempts=30,turnovers=2,fumblesLost=1,interceptions=1),dict(game_id=2,team_id=10,rushingYards=999,rushingAttempts=10,turnovers=0,fumblesLost=0,interceptions=0)])
        return pd.DataFrame([old,fcs,g]),b
    def test_profiles_exclude_fcs_and_no_pass_dependency(self):
        s,b=self.history();r=build_waterfall_profiles(s,b,3)['3']
        self.assertEqual(r['home'],dict(off_run=6,def_run=4,margin=2,games=1))
    def test_incomplete_history_fails_closed(self):
        s,b=self.history()
        for bad in [b.iloc[:1],pd.concat([b,b.iloc[:1]]),b.assign(turnovers=9),pd.DataFrame()]:
            self.assertNotEqual(build_waterfall_profiles(s,bad,3).get('3',{}).get('status'),'ok')
    def test_no_future_same_week_or_other_season(self):
        s,b=self.history()
        for col,value in [('season',2025),('week',3),('start_date','2026-09-20T12:00:00Z')]:
            changed=s.copy();changed.loc[0,col]=value
            self.assertEqual(build_waterfall_profiles(changed,b,3)['3']['status'],'missing')
    def test_sac_season_override(self):
        g,_,_=self.fixture();g.update(home_team='Sacramento State',home_division='fcs')
        self.assertEqual(len(normalize_fbs_schedule(pd.DataFrame([g]))),1)
        g.update(season=2025,home_division='fbs');self.assertTrue(normalize_fbs_schedule(pd.DataFrame([g])).empty)
    def test_annotation_and_scenario_do_not_change_model(self):
        s,b=self.history();_,p,_=self.fixture();p.update({'Game ID':3,'Status':'Final','Actual Winner':'Home','Home Win %':.25,'Away Win %':.75})
        # Home defensive YPC=4 vs away 6, offensive 6 vs away 4.
        out=add_waterfall_value(pd.DataFrame([p]),s,b,3)
        self.assertEqual(out.iloc[0]['Predicted Winner'],'Away')
        self.assertEqual(out.iloc[0]['Value Result'],'Correct')
        sim=waterfall_scenario_rows(out)
        self.assertEqual(sim.iloc[0]['Predicted Winner'],'Home');self.assertEqual(sim.iloc[0]['Bet Line'],'+120')
        self.assertEqual(out.iloc[0]['Predicted Winner'],'Away')

if __name__=='__main__':unittest.main()

class IntegrationTests(unittest.TestCase):
    def api_functions(self):
        import ast
        from pathlib import Path
        tree=ast.parse(Path('backend/main.py').read_text())
        wanted={'attach_market_context','_implied','json_rows'}
        ns={'pd':pd,'json':__import__('json')}
        ns['odds']=lambda _: {'quotes':{'1':{'DraftKings':dict(home_id='10',away_id='20',home='+120',away='-140')}}}
        body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in wanted]
        exec(compile(ast.Module(body=body,type_ignores=[]),'backend/main.py','exec'),ns)
        return ns
    def test_api_preserves_dk_and_no_edge_labels(self):
        g,p,_=WaterfallTests().fixture();p.update({'Home Team':'Home','Away Team':'Away','Predicted Side':'Away'})
        ns=self.api_functions();out=ns['attach_market_context'](pd.DataFrame([p]),pd.DataFrame([g]))
        self.assertEqual(out.iloc[0]['DK Home ML'],'+120');self.assertNotIn('Bet Signal',out)
        self.assertEqual(len(ns['json_rows'](out)),1)
    def test_scenario_profit_uses_underdog(self):
        import ast,numpy as np
        from pathlib import Path
        from decimal import Decimal,ROUND_HALF_UP
        ns=dict(pd=pd,np=np,math=__import__("math"),Decimal=Decimal,ROUND_HALF_UP=ROUND_HALF_UP)
        tree=ast.parse(Path('app.py').read_text());names={'simulate_stakes','format_moneyline','payout_outcomes'}
        exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),'app.py','exec'),ns)
        s,b=WaterfallTests().history();_,p,_=WaterfallTests().fixture()
        p.update({'Game ID':3,'Week':3,'Home Team':'Home','Away Team':'Away','Status':'Final','Actual Winner':'Home','Home Win %':.25,'Away Win %':.75})
        rows=waterfall_scenario_rows(add_waterfall_value(pd.DataFrame([p]),s,b,3))
        out=ns['simulate_stakes'](rows,{x:10 for x in ('High','Moderate','Lean','Toss-up')})
        self.assertEqual(out.iloc[0]['Net Profit'],12);self.assertTrue(out.iloc[0]['Won'])
