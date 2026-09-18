"""Validate production candidate against independent historical calculations."""
import ast, importlib.util, sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import expit,logit
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backtests'))
from conference_audit import normalize
path=ROOT/'model_v1_5_candidate.py'
if not path.exists():path=ROOT/'model.py'
spec=importlib.util.spec_from_file_location('candidate',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
g={'season':2026,'season_type':'regular','home_division':'fbs','away_division':'fbs','home_conference':'SEC','away_conference':'American Athletic'}
assert m.conference_log_odds(g)==m.CONFERENCE_LOG_ODDS
assert m.conference_log_odds(dict(g,home_conference='American Athletic',away_conference='SEC'))==-m.CONFERENCE_LOG_ODDS
for changes in [dict(season_type='postseason'),dict(away_division='fcs'),dict(away_conference='SEC'),dict(away_conference='FBS Independents'),dict(home_conference='Unknown'),dict(season=None),dict(season=2021)]:
    assert m.conference_log_odds(dict(g,**changes))==0
assert m.conference_log_odds(dict(g,season=2023,home_conference='Pac-12'))==m.CONFERENCE_LOG_ODDS
assert m.conference_log_odds(dict(g,season=2024,away_conference='Pac-12'))==0
assert m.conference_log_odds(dict(g,season=2026,away_conference='Pac-12'))==m.CONFERENCE_LOG_ODDS
tree=ast.parse((ROOT/'app.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='augment_missing_summaries')
ns={'pd':pd};exec(compile(ast.Module(body=[fn],type_ignores=[]),'app.py','exec'),ns)
for year in [2024,2025]:
    s=normalize(pd.read_csv(ROOT/f'schedule{year}.csv'))
    cur=pd.read_csv(ROOT/f'summary{year}.csv',low_memory=False);prior=pd.read_csv(ROOT/f'summary{year-1}.csv',low_memory=False)
    frames=[]
    for week in sorted(s.week.unique()):
        c,_=ns['augment_missing_summaries'](cur,prior,s,week)
        frames.append(m.predict_week(c,prior,s,int(week),include_completed=True))
    actual=pd.concat(frames).set_index('Game ID')
    original=pd.read_csv(ROOT/f'backtests/extended_baseline_{year}.csv').set_index('game_id')
    got=actual.loc[original.index,'Home Win %'].to_numpy()
    expected=expit(logit(original.p)+m.CONFERENCE_LOG_ODDS*original.sign).to_numpy()
    np.testing.assert_allclose(got,expected,atol=1e-12,rtol=0)
    np.testing.assert_allclose(actual['Home Win %']+actual['Away Win %'],1,atol=1e-12)
    assert actual['Home Win %'].between(0,1).all()
    assert actual['Model Version'].eq('V1.5').all()
    print(year,len(got),'predictions matched independent candidate calculation')
print('PASS: scope, era classification, symmetry, probability bounds and historical parity')
