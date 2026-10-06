from pathlib import Path
import sys, json, math, time
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
OUT=Path(__file__).resolve().parent
OUT.mkdir(parents=True,exist_ok=True)

from model_v1_5 import predict_week
import matchup_advantages as ma
from matchup_advantages import build_waterfall_profiles, normalize_fbs_schedule

SEASON=2020
P4={'ACC','Big Ten','Big 12','SEC','Pac-12'}
G5={'American Athletic','Conference USA','Mid-American','Mountain West','Sun Belt'}
ma.P4=set(P4);ma.G6=set(G5)

def csv_url(url):
    with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 tier4-2020-holdout'}),timeout=90) as r:return pd.read_csv(r,low_memory=False)
def js(url,tries=3):
    last=None
    for i in range(tries):
        try:
            with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 tier4-2020-holdout'}),timeout=25) as r:return json.load(r)
        except Exception as e:last=e;time.sleep(.4*(i+1))
    raise last
def num(v):
    try:
        s=str(v).strip().replace('+','').replace('−','-');x=float(s);return x if math.isfinite(x) else None
    except:return None
def qside(o,side):
    ml=(o.get('moneyline') or {}).get(side,{})
    money=num((ml.get('close') or {}).get('odds'))
    if money is None:money=num((o.get(side+'TeamOdds') or {}).get('moneyLine'))
    ps=(o.get('pointSpread') or {}).get(side,{})
    spread=num((ps.get('close') or {}).get('line'))
    team=o.get(side+'TeamOdds') or {}
    if spread is None:
        raw=num(o.get('spread'))
        if raw is not None:
            if team.get('favorite') is True:spread=-abs(raw)
            elif team.get('underdog') is True:spread=abs(raw)
    return money,spread
def parse(o):
    hm,hs=qside(o,'home');am,as_=qside(o,'away')
    return {'home_ml':hm,'away_ml':am,'home_spread':hs,'away_spread':as_}
def quote(gid):
    try:
        q=parse(js(f'https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/events/{gid}/competitions/{gid}/odds/58?lang=en&region=us'))
        if q['home_ml'] is not None and q['away_ml'] is not None:return gid,q,None
    except Exception:pass
    try:
        p=js(f'https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event={gid}')
        for o in p.get('pickcenter',[]) or []:
            q=parse(o)
            if q['home_ml'] is not None and q['away_ml'] is not None:return gid,q,None
        return gid,None,'no paired odds'
    except Exception as e:return gid,None,repr(e)

schedule=csv_url('https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_2020.csv')
boxes=csv_url('https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_2020.csv')
cur=csv_url('https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_2020.csv')
prior=csv_url('https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_2019.csv')
s=normalize_fbs_schedule(schedule);s=s[s.season_type.astype(str).str.lower().eq('regular')]

pref=[]
for week in sorted(pd.to_numeric(s.week,errors='coerce').dropna().astype(int).unique()):
    pred=predict_week(cur,prior,schedule,week,include_completed=True)
    prof=build_waterfall_profiles(schedule,boxes,week)
    pm={int(x['Game ID']):x for x in pred.to_dict('records') if pd.notna(x.get('Game ID'))}
    for _,g in s[pd.to_numeric(s.week,errors='coerce').eq(week)].iterrows():
        try:gid=int(g.game_id)
        except:continue
        p=pm.get(gid);rec=prof.get(str(gid),{})
        if p is None or rec.get('status')!='ok':continue
        conf=num(p.get('Confidence'))
        if conf is None or not (.70<=conf<.80):continue
        side=str(p.get('Predicted Side','')).strip().lower()
        if side not in ('home','away'):continue
        other='away' if side=='home' else 'home';f,d=rec[side],rec[other]
        if not (f['def_run']<d['off_run'] and f['margin']>d['margin']):continue
        hp=num(g.get('home_points'));ap=num(g.get('away_points'))
        if hp is None or ap is None:continue
        pref.append({'season':SEASON,'week':week,'game_id':gid,'home':g.home_team,'away':g.away_team,
          'predicted_side':side,'pick':g[side+'_team'],'confidence':conf,
          'turnover_edge':f['margin']-d['margin'],'fav_def_ypc':f['def_run'],'dog_off_ypc':d['off_run'],
          'home_points':hp,'away_points':ap})

quotes={};errs=[]
with ThreadPoolExecutor(max_workers=12) as ex:
    futs={ex.submit(quote,x['game_id']):x for x in pref}
    for f in as_completed(futs):
        gid,q,e=f.result()
        if q:quotes[gid]=q
        else:errs.append({'game_id':gid,'error':e})
rows=[]
for r in pref:
    q=quotes.get(r['game_id'])
    if not q:continue
    side=r['predicted_side'];other='away' if side=='home' else 'home'
    fav=q[side+'_ml'];dog=q[other+'_ml']
    if fav is None or dog is None or not (-500<=fav<=-400 and dog>0):continue
    margin=(r['home_points']-r['away_points']) if side=='home' else (r['away_points']-r['home_points'])
    x=dict(r);x.update(favorite_ml=fav,underdog_ml=dog,favorite_spread=q[side+'_spread'],margin=margin,win=margin>0,
      ml_profit_10=(10*100/abs(fav)) if margin>0 else -10)
    rows.append(x)
out=pd.DataFrame(rows)
out.to_csv(OUT/'tier4_2020_holdout.csv',index=False)
pd.DataFrame(errs).to_csv(OUT/'tier4_2020_errors.csv',index=False)
n=len(out);w=int(out.win.sum()) if n else 0;p=float(out.ml_profit_10.sum()) if n else 0
summary={'frozen_rule':{'favorite_ml':'-400 through -500','confidence':'70% to under 80%',
'run_defense':'favorite defensive YPC < underdog offensive YPC','turnovers':'favorite turnover margin/game strictly better',
'market':'favorite ML','group':'no group restriction','venue':'no venue restriction'},
'coverage':{'prefilter':len(pref),'quotes':len(quotes),'errors':len(errs),'qualifiers':n},
'result':{'record':f'{w}-{n-w}','win_rate':w/n if n else None,'roi':p/(10*n) if n else None},
'games':out.to_dict('records') if n else []}
(OUT/'tier4_2020_summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
