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
ma.P4=set(P4); ma.G6=set(G5)

def csv_url(url):
    with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 tier4-2021-holdout'}),timeout=90) as r:
        return pd.read_csv(r,low_memory=False)

def fetch_json(url,tries=3,timeout=25):
    last=None
    for i in range(tries):
        try:
            with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 tier4-2021-holdout'}),timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            last=e; time.sleep(.4*(i+1))
    raise last

def num(v):
    try:
        s=str(v).strip().replace('+','').replace('−','-')
        if not s or s.lower() in ('nan','none','null','unavailable'):return None
        x=float(s);return x if math.isfinite(x) else None
    except:return None

def quote_side(o,side):
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
    hm,hs=quote_side(o,'home');am,as_=quote_side(o,'away')
    return {'home_ml':hm,'away_ml':am,'home_spread':hs,'away_spread':as_,
            'provider':str((o.get('provider') or {}).get('name') or '').strip()}

def fetch_quote(gid):
    urls=[
      f'https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/events/{gid}/competitions/{gid}/odds/58?lang=en&region=us',
      f'https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event={gid}'
    ]
    try:
        # Try archived provider first.
        try:
            q=parse(fetch_json(urls[0]))
            if q['home_ml'] is not None and q['away_ml'] is not None:return gid,q,None
        except Exception:
            pass
        payload=fetch_json(urls[1])
        opts=[parse(x) for x in (payload.get('pickcenter') or [])]
        opts=[x for x in opts if x['home_ml'] is not None and x['away_ml'] is not None]
        if opts:return gid,opts[0],None
        return gid,None,'no paired archived moneyline'
    except Exception as e:return gid,None,repr(e)

schedule=csv_url('https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_2021.csv')
boxes=csv_url('https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_2021.csv')
cur=csv_url('https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_2021.csv')
prior=csv_url('https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_2020.csv')

s=normalize_fbs_schedule(schedule)
s=s[s.season_type.astype(str).str.lower().eq('regular')]
pref=[]
for week in sorted(pd.to_numeric(s.week,errors='coerce').dropna().astype(int).unique()):
    pred=predict_week(cur,prior,schedule,week,include_completed=True)
    profiles=build_waterfall_profiles(schedule,boxes,week)
    pmap={int(x['Game ID']):x for x in pred.to_dict('records') if pd.notna(x.get('Game ID'))}
    target=s[pd.to_numeric(s.week,errors='coerce').eq(week)]
    for _,g in target.iterrows():
        try:gid=int(g.game_id)
        except:continue
        p=pmap.get(gid);rec=profiles.get(str(gid),{})
        if p is None or rec.get('status')!='ok':continue
        # P4 vs P4 only, Notre Dame treated as P4.
        def is_p4(conf,team):return str(team).strip().casefold()=='notre dame' or str(conf).strip() in P4
        if not (is_p4(g.get('home_conference'),g.get('home_team')) and is_p4(g.get('away_conference'),g.get('away_team'))):continue
        conf=num(p.get('Confidence'))
        if conf is None or not (.70<=conf<.80):continue
        side=str(p.get('Predicted Side','')).strip().lower()
        if side!='away':continue  # frozen candidate requires road favorite
        f,d=rec['away'],rec['home']
        if not (f['def_run']<d['off_run'] and f['margin']>d['margin']):continue
        hp=num(g.get('home_points'));ap=num(g.get('away_points'))
        if hp is None or ap is None:continue
        pref.append({'season':SEASON,'week':week,'game_id':gid,'home':g.home_team,'away':g.away_team,
          'pick':g.away_team,'confidence':conf,'turnover_edge':f['margin']-d['margin'],
          'fav_def_ypc':f['def_run'],'dog_off_ypc':d['off_run'],'home_points':hp,'away_points':ap})

quotes={};errs=[]
with ThreadPoolExecutor(max_workers=12) as ex:
    futs={ex.submit(fetch_quote,x['game_id']):x for x in pref}
    for f in as_completed(futs):
        gid,q,e=f.result()
        if q:quotes[gid]=q
        else:errs.append({'game_id':gid,'error':e})

rows=[]
for r in pref:
    q=quotes.get(r['game_id'])
    if not q:continue
    fav=q['away_ml'];dog=q['home_ml']
    if fav is None or dog is None or not (-600<=fav<=-280 and dog>0):continue
    margin=r['away_points']-r['home_points'];win=margin>0
    x=dict(r);x.update(favorite_ml=fav,underdog_ml=dog,favorite_spread=q['away_spread'],
      margin=margin,win=win,ml_profit_10=(10*100/abs(fav)) if win else -10)
    rows.append(x)

out=pd.DataFrame(rows)
out.to_csv(OUT/'tier4_2021_holdout.csv',index=False)
pd.DataFrame(errs).to_csv(OUT/'tier4_2021_errors.csv',index=False)
n=len(out);w=int(out.win.sum()) if n else 0;p=float(out.ml_profit_10.sum()) if n else 0
summary={'frozen_rule':{'matchup':'P4 vs P4','venue':'favorite on road','favorite_ml':'-280 through -600',
'confidence':'70% to under 80%','run_defense':'favorite defensive YPC < underdog offensive YPC',
'turnovers':'favorite turnover margin/game strictly better','market':'favorite ML'},
'coverage':{'prefilter':len(pref),'quotes':len(quotes),'errors':len(errs),'qualifiers':n},
'result':{'record':f'{w}-{n-w}','win_rate':w/n if n else None,'roi':p/(10*n) if n else None},
'games':out.to_dict('records') if n else []}
(OUT/'tier4_2021_summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
