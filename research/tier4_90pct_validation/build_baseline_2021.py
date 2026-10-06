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

SEASON=2021
P4={'ACC','Big Ten','Big 12','SEC','Pac-12'}
G5={'American Athletic','Conference USA','Mid-American','Mountain West','Sun Belt'}
ma.P4=set(P4);ma.G6=set(G5)

def csv_url(url):
    with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 tier4-baseline-2021'}),timeout=90) as r:return pd.read_csv(r,low_memory=False)
def js(url,tries=3):
    last=None
    for i in range(tries):
        try:
            with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 tier4-baseline-2021'}),timeout=25) as r:return json.load(r)
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
        url=f'https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/events/{gid}/competitions/{gid}/odds/58?lang=en&region=us'
        q=parse(js(url))
        if q['home_ml'] is not None and q['away_ml'] is not None:return gid,q,None
    except Exception:pass
    try:
        p=js(f'https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event={gid}')
        for o in p.get('pickcenter',[]) or []:
            q=parse(o)
            if q['home_ml'] is not None and q['away_ml'] is not None:return gid,q,None
        return gid,None,'no paired odds'
    except Exception as e:return gid,None,repr(e)

schedule=csv_url('https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_2021.csv')
boxes=csv_url('https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_2021.csv')
cur=csv_url('https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_2021.csv')
prior=csv_url('https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_2020.csv')
s=normalize_fbs_schedule(schedule);s=s[s.season_type.astype(str).str.lower().eq('regular')]

def grp(conf,team):
    if str(team).strip().casefold()=='notre dame':return 'P4'
    c=str(conf).strip()
    return 'P4' if c in P4 else 'G6' if c in G5 else None

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
        if conf is None or conf<.70:continue
        side=str(p.get('Predicted Side','')).strip().lower()
        if side not in ('home','away'):continue
        other='away' if side=='home' else 'home';f,d=rec[side],rec[other]
        if not (f['def_run']<d['off_run'] and f['margin']>=d['margin']):continue
        hp=num(g.get('home_points'));ap=num(g.get('away_points'))
        if hp is None or ap is None:continue
        hg=grp(g.get('home_conference'),g.get('home_team'));ag=grp(g.get('away_conference'),g.get('away_team'))
        group='P4/P4' if hg=='P4' and ag=='P4' else 'G6/G6' if hg=='G6' and ag=='G6' else 'Mixed/Other'
        pref.append({'season':SEASON,'week':week,'game_id':gid,'home':g.home_team,'away':g.away_team,
          'predicted_side':side,'predicted_team':g[side+'_team'],'confidence':conf,'group':group,
          'favorite_venue':'Home' if side=='home' else 'Road','fav_def_ypc':f['def_run'],'dog_off_ypc':d['off_run'],
          'turnover_edge':f['margin']-d['margin'],'home_points':hp,'away_points':ap})

quotes={};errs=[]
with ThreadPoolExecutor(max_workers=16) as ex:
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
    if fav is None or dog is None or not (-600<=fav<=-280 and dog>0):continue
    margin=(r['home_points']-r['away_points']) if side=='home' else (r['away_points']-r['home_points'])
    x=dict(r);x.update(favorite_ml=fav,underdog_ml=dog,favorite_spread=q[side+'_spread'],margin=margin,win=margin>0,
      ml_profit_10=(10*100/abs(fav)) if margin>0 else -10)
    rows.append(x)
out=pd.DataFrame(rows)
out.to_csv(OUT/'baseline_2021.csv',index=False)
pd.DataFrame(errs).to_csv(OUT/'baseline_2021_errors.csv',index=False)
print(json.dumps({'prefilter':len(pref),'quotes':len(quotes),'qualifiers':len(out),'errors':len(errs)},indent=2))
