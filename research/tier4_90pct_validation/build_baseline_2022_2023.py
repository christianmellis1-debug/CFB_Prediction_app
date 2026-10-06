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

SEASONS=(2022,2023)
HIST_P4={'ACC','Big Ten','Big 12','SEC','Pac-12'}
HIST_G5={'American Athletic','Conference USA','Mid-American','Mountain West','Sun Belt'}
ma.P4=set(HIST_P4); ma.G6=set(HIST_G5)

def csv_url(url):
    with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 tier4-full-history'}),timeout=90) as r:
        return pd.read_csv(r,low_memory=False)

def fetch_json(url,tries=3,timeout=25):
    last=None
    for i in range(tries):
        try:
            with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 tier4-full-history'}),timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            last=e; time.sleep(.4*(i+1))
    raise last

def num(v):
    try:
        s=str(v).strip().replace('+','').replace('−','-')
        if not s or s.lower() in ('nan','none','null','unavailable'): return None
        x=float(s); return x if math.isfinite(x) else None
    except: return None

def grp(conf,team):
    if str(team).strip().casefold()=='notre dame': return 'P4'
    c=str(conf).strip()
    return 'P4' if c in HIST_P4 else 'G6' if c in HIST_G5 else None

def quote_side(o,side):
    ml=(o.get('moneyline') or {}).get(side,{})
    money=num((ml.get('close') or {}).get('odds'))
    if money is None: money=num((o.get(side+'TeamOdds') or {}).get('moneyLine'))
    ps=(o.get('pointSpread') or {}).get(side,{})
    spread=num((ps.get('close') or {}).get('line'))
    spread_price=num((ps.get('close') or {}).get('odds'))
    team=o.get(side+'TeamOdds') or {}
    if spread is None:
        raw=num(o.get('spread'))
        if raw is not None:
            if team.get('favorite') is True: spread=-abs(raw)
            elif team.get('underdog') is True: spread=abs(raw)
    if spread_price is None: spread_price=num(team.get('spreadOdds'))
    return money,spread,spread_price

def parse_provider(o):
    hm,hs,hsp=quote_side(o,'home'); am,as_,asp=quote_side(o,'away')
    return dict(provider=str((o.get('provider') or {}).get('name') or '').strip(),
                home_ml=hm,away_ml=am,home_spread=hs,away_spread=as_,
                home_spread_price=hsp,away_spread_price=asp)

def fetch_quote(item):
    gid=item['game_id']
    try:
        url=f'https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/events/{gid}/competitions/{gid}/odds/58?lang=en&region=us'
        q=parse_provider(fetch_json(url))
        if q['home_ml'] is None or q['away_ml'] is None:return gid,None,'missing paired moneyline'
        return gid,q,None
    except Exception as e:return gid,None,repr(e)

summaries={}
for y in (2021,2022,2023):
    summaries[y]=csv_url(f'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_{y}.csv')
schedules={};boxes={}
for y in SEASONS:
    schedules[y]=csv_url(f'https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{y}.csv')
    boxes[y]=csv_url(f'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_{y}.csv')

prefilter=[]
for season in SEASONS:
    raw=schedules[season]; s=normalize_fbs_schedule(raw)
    s=s[s.season_type.astype(str).str.lower().eq('regular')]
    for week in sorted(pd.to_numeric(s.week,errors='coerce').dropna().astype(int).unique()):
        pred=predict_week(summaries[season],summaries[season-1],raw,week,include_completed=True)
        profiles=build_waterfall_profiles(raw,boxes[season],week)
        pmap={int(x['Game ID']):x for x in pred.to_dict('records') if pd.notna(x.get('Game ID'))}
        target=s[pd.to_numeric(s.week,errors='coerce').eq(week)]
        for _,g in target.iterrows():
            try:gid=int(g.game_id)
            except:continue
            p=pmap.get(gid); rec=profiles.get(str(gid),{})
            if p is None or rec.get('status')!='ok':continue
            conf=num(p.get('Confidence'))
            if conf is None or conf<.70:continue
            side=str(p.get('Predicted Side','')).strip().lower()
            if side not in ('home','away'):continue
            other='away' if side=='home' else 'home'
            f,d=rec[side],rec[other]
            if not (f['def_run']<d['off_run'] and f['margin']>=d['margin']):continue
            hp=num(g.get('home_points'));ap=num(g.get('away_points'))
            if hp is None or ap is None:continue
            hg=grp(g.get('home_conference'),g.get('home_team'));ag=grp(g.get('away_conference'),g.get('away_team'))
            group='P4/P4' if hg=='P4' and ag=='P4' else 'G6/G6' if hg=='G6' and ag=='G6' else 'Mixed/Other'
            prefilter.append(dict(season=season,week=week,game_id=gid,home=g.home_team,away=g.away_team,
                predicted_side=side,predicted_team=g[side+'_team'],confidence=conf,group=group,
                favorite_venue='Home' if side=='home' else 'Road',
                fav_def_ypc=f['def_run'],dog_off_ypc=d['off_run'],
                turnover_edge=f['margin']-d['margin'],home_points=hp,away_points=ap))

quotes={};errs=[]
with ThreadPoolExecutor(max_workers=20) as ex:
    futs={ex.submit(fetch_quote,x):x for x in prefilter}
    for f in as_completed(futs):
        gid,q,e=f.result()
        if q:quotes[gid]=q
        else:errs.append({'game_id':gid,'error':e})

rows=[]
for r in prefilter:
    q=quotes.get(r['game_id'])
    if not q:continue
    side=r['predicted_side'];other='away' if side=='home' else 'home'
    fav=q[side+'_ml'];dog=q[other+'_ml']
    if fav is None or dog is None or not (-600<=fav<=-280 and dog>0):continue
    margin=(r['home_points']-r['away_points']) if side=='home' else (r['away_points']-r['home_points'])
    x=dict(r);x.update(favorite_ml=fav,underdog_ml=dog,favorite_spread=q[side+'_spread'],
       spread_price=q[side+'_spread_price'],margin=margin,win=margin>0,
       ml_profit_10=(10*100/abs(fav)) if margin>0 else -10)
    rows.append(x)

out=pd.DataFrame(rows)
out.to_csv(OUT/'baseline_2022_2023.csv',index=False)
pd.DataFrame(errs).to_csv(OUT/'baseline_fetch_errors.csv',index=False)
print(json.dumps({'prefilter':len(prefilter),'quotes':len(quotes),'qualifiers':len(out),'errors':len(errs)},indent=2))
