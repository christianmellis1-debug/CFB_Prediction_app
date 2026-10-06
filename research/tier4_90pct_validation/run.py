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
from matchup_advantages import build_waterfall_profiles, normalize_fbs_schedule

SEASONS=(2022,2023)
HISTORICAL_POWER={'ACC','Big Ten','Big 12','SEC','Pac-12'}

def csv_url(url):
    with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 tier4-90pct-holdout'}),timeout=90) as r:
        return pd.read_csv(r,low_memory=False)

def fetch_json(url,tries=3,timeout=25):
    last=None
    for i in range(tries):
        try:
            with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 tier4-90pct-holdout'}),timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            last=e
            time.sleep(.4*(i+1))
    raise last

def num(v):
    try:
        s=str(v).strip().replace('+','').replace('−','-')
        if not s or s.lower() in ('nan','none','null','unavailable'): return None
        x=float(s)
        return x if math.isfinite(x) else None
    except:
        return None

def is_power(conf,team):
    if str(team).strip().casefold()=='notre dame':
        return True
    return str(conf).strip() in HISTORICAL_POWER

def quote_side(o,side):
    ml=(o.get('moneyline') or {}).get(side,{})
    money=num((ml.get('close') or {}).get('odds'))
    if money is None:
        money=num((o.get(side+'TeamOdds') or {}).get('moneyLine'))
    ps=(o.get('pointSpread') or {}).get(side,{})
    spread=num((ps.get('close') or {}).get('line'))
    spread_price=num((ps.get('close') or {}).get('odds'))
    team=o.get(side+'TeamOdds') or {}
    if spread is None:
        raw=num(o.get('spread'))
        if raw is not None:
            if team.get('favorite') is True: spread=-abs(raw)
            elif team.get('underdog') is True: spread=abs(raw)
    if spread_price is None:
        spread_price=num(team.get('spreadOdds'))
    return money,spread,spread_price

def parse_provider(o):
    hm,hs,hsp=quote_side(o,'home'); am,as_,asp=quote_side(o,'away')
    return dict(provider=str((o.get('provider') or {}).get('name') or '').strip(),
                home_ml=hm,away_ml=am,home_spread=hs,away_spread=as_,
                home_spread_price=hsp,away_spread_price=asp,details=o.get('details'))

def fetch_quote(item):
    gid=item['game_id']
    try:
        url=f'https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/events/{gid}/competitions/{gid}/odds/58?lang=en&region=us'
        q=parse_provider(fetch_json(url))
        if not q['provider']: q['provider']='ESPN BET'
        q['url']=url
        if q['home_ml'] is None or q['away_ml'] is None:
            return gid,None,'missing paired moneyline'
        return gid,q,None
    except Exception as e:
        return gid,None,repr(e)

schedules={}; boxes={}; summaries={}
for year in (2021,2022,2023):
    summaries[year]=csv_url(
      f'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_{year}.csv'
    )
for year in SEASONS:
    schedules[year]=csv_url(f'https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{year}.csv')
    boxes[year]=csv_url(f'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_{year}.csv')

prefilter=[]
for season in SEASONS:
    raw=schedules[season]
    s=normalize_fbs_schedule(raw).copy()
    s=s[s.season_type.astype(str).str.lower().eq('regular')]
    for week in sorted(pd.to_numeric(s.week,errors='coerce').dropna().astype(int).unique()):
        pred=predict_week(summaries[season],summaries[season-1],raw,week,include_completed=True)
        profiles=build_waterfall_profiles(raw,boxes[season],week)
        pmap={int(x['Game ID']):x for x in pred.to_dict('records') if pd.notna(x.get('Game ID'))}
        target=s[pd.to_numeric(s.week,errors='coerce').eq(week)]
        for _,g in target.iterrows():
            try: gid=int(g.game_id)
            except: continue
            p=pmap.get(gid)
            rec=profiles.get(str(gid),{})
            # build_waterfall_profiles may mark Pac-12/P4 games outside under today's
            # classification. Recompute metrics only if profile is available; otherwise
            # this game cannot be scored consistently with the production metric builder.
            if p is None or rec.get('status')!='ok':
                continue
            if not (is_power(g.get('home_conference'),g.get('home_team')) and
                    is_power(g.get('away_conference'),g.get('away_team'))):
                continue
            conf=num(p.get('Confidence'))
            if conf is None or not (.70 <= conf < .80):
                continue
            side=str(p.get('Predicted Side','')).strip().lower()
            if side not in ('home','away'):
                continue
            other='away' if side=='home' else 'home'
            f,d=rec[side],rec[other]
            if not (f['def_run'] < d['off_run'] and f['margin'] > d['margin']):
                continue
            hp=num(g.get('home_points')); ap=num(g.get('away_points'))
            if hp is None or ap is None:
                continue
            prefilter.append({
                'season':season,'week':week,'game_id':gid,
                'home':g.home_team,'away':g.away_team,
                'predicted_side':side,'predicted_team':g[side+'_team'],
                'confidence':conf,'favorite_conference':g.get(side+'_conference'),
                'underdog_conference':g.get(other+'_conference'),
                'fav_def_ypc':f['def_run'],'dog_off_ypc':d['off_run'],
                'predicted_to_margin':f['margin'],'other_to_margin':d['margin'],
                'turnover_edge':f['margin']-d['margin'],
                'home_points':hp,'away_points':ap
            })

print('candidate games before odds gate',len(prefilter),flush=True)

quotes={}; errors=[]
with ThreadPoolExecutor(max_workers=18) as ex:
    futs={ex.submit(fetch_quote,x):x for x in prefilter}
    for f in as_completed(futs):
        gid,q,e=f.result()
        if q is not None: quotes[gid]=q
        else: errors.append({'game_id':gid,'error':e})

rows=[]
for r in prefilter:
    q=quotes.get(r['game_id'])
    if not q: continue
    side=r['predicted_side']; other='away' if side=='home' else 'home'
    fav_ml=q[side+'_ml']; dog_ml=q[other+'_ml']
    if fav_ml is None or dog_ml is None or not (-450 <= fav_ml <= -280 and dog_ml>0):
        continue
    margin=(r['home_points']-r['away_points']) if side=='home' else (r['away_points']-r['home_points'])
    win=margin>0
    ml_profit=(10*100/abs(fav_ml)) if win else -10
    spread=q.get(side+'_spread'); sp=q.get(side+'_spread_price')
    ats_margin=(margin+spread) if spread is not None else None
    ats='W' if ats_margin is not None and ats_margin>1e-9 else 'L' if ats_margin is not None and ats_margin<-1e-9 else 'P' if ats_margin is not None else 'Missing'
    x=dict(r)
    x.update(provider=q['provider'],favorite_ml=fav_ml,underdog_ml=dog_ml,
             favorite_spread=spread,spread_price=sp,margin=margin,win=win,
             ml_profit_10=ml_profit,ats_result=ats)
    rows.append(x)

out=pd.DataFrame(rows)
out.to_csv(OUT/'tier4_90pct_holdout_games.csv',index=False)
pd.DataFrame(prefilter).to_csv(OUT/'prefilter_candidates.csv',index=False)
pd.DataFrame(errors).to_csv(OUT/'fetch_errors.csv',index=False)

def stat(frame):
    n=len(frame)
    if not n: return {'n':0,'w':0,'l':0,'pct':None,'roi':None}
    w=int(frame.win.sum()); l=n-w
    p=float(frame.ml_profit_10.sum())
    return {'n':n,'w':w,'l':l,'pct':w/n,'roi':p/(10*n)}

summary={
 'frozen_rule':{
   'matchup':'historical P4 vs P4 only; Notre Dame treated as P4; Pac-12 power in 2022-23',
   'favorite_ml':'-280 through -450 inclusive',
   'model_confidence':'70% to under 80%',
   'run_defense':'favorite defensive YPC allowed < underdog offensive YPC',
   'turnovers':'favorite turnover margin/game strictly greater than underdog',
   'market':'favorite moneyline'
 },
 'coverage':{'prefilter':len(prefilter),'quotes':len(quotes),'fetch_errors':len(errors),'qualifiers':len(out)},
 'overall':stat(out),
 'by_season':{str(y):stat(out[out.season.eq(y)]) for y in SEASONS},
 'games':out[['season','week','game_id','away','home','predicted_team','confidence','favorite_ml','favorite_spread','turnover_edge','win','ats_result']].to_dict('records') if len(out) else []
}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2),flush=True)
