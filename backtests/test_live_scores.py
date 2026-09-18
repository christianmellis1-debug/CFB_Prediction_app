"""Scores may render live, but results may settle only on explicit finals."""
import ast, copy, sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from live_scores import parse_live_scores, overlay_live_scores
path=ROOT/'live_scores_app.py'
if not path.exists():path=ROOT/'app.py'
tree=ast.parse(path.read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='attach_results')
ns={'pd':pd};exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
games=pd.DataFrame([dict(game_id=1,home_id=10,away_id=20,home_team='Home',away_team='Away',completed=False,home_points=None,away_points=None)])
picks=pd.DataFrame([{'Game ID':1,'Home Team':'Home','Away Team':'Away','Predicted Winner':'Home','Confidence':.7}])
payload={'events':[{'id':'1','competitions':[{'competitors':[{'homeAway':'home','team':{'id':'10'},'score':'17'},{'homeAway':'away','team':{'id':'20'},'score':'10'}],'status':{'type':{'state':'in','completed':False,'detail':'Halftime'}}}]}]}
def apply(p):return ns['attach_results'](picks,overlay_live_scores(games,parse_live_scores(p)))
r=apply(payload).iloc[0]
assert r['Status']=='In progress' and r['Pick Result']=='Pending' and r['Actual Winner']=='—'
assert r['Live Score']=='Away 10 – Home 17' and r['Live Detail']=='Halftime'
assert games.iloc[0].completed==False and pd.isna(games.iloc[0].home_points)
assert r['Confidence']==.7
p=copy.deepcopy(payload);p['events'][0]['competitions'][0]['status']['type']={'state':'post','completed':True,'detail':'Final'}
r=apply(p).iloc[0];assert r['Status']=='Final' and r['Actual Winner']=='Home' and r['Pick Result']=='Correct'
p['events'][0]['competitions'][0]['competitors'][0]['score']=None
assert apply(p).iloc[0]['Pick Result']=='Pending'
p=copy.deepcopy(payload);p['events'][0]['competitions'][0]['competitors'][0]['team']['id']='999'
assert apply(p).iloc[0]['Status']=='Awaiting final'
finished=games.copy();finished['completed']=True;finished['home_points']=24;finished['away_points']=10
assert overlay_live_scores(finished,parse_live_scores(payload)).iloc[0].home_points==24
assert parse_live_scores({'events':[]})=={}
print('PASS: live/halftime, final settlement, missing scores, team identity, final regression, model isolation')
