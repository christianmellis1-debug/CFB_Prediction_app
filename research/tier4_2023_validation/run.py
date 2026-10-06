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

SEASON=2023

def csv_url(url):
    with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 tier4-2023-validation'}),timeout=90) as r:
        return pd.read_csv(r,low_memory=False)

def fetch_json(url,tries=3,timeout=25):
    last=None
    for i in range(tries):
        try:
            with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 tier4-2023-validation'}),timeout=timeout) as r:
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
    except: return None

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

def fetch_quote(gid):
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

schedule=csv_url('https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_2023.csv')
boxes=csv_url('https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_2023.csv')
cur=csv_url('https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_2023.csv')
prior=csv_url('https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_2022.csv')

s=normalize_fbs_schedule(schedule).copy()
s=s[s.season_type.astype(str).str.lower().eq('regular')]

prefilter=[]
for week in sorted(pd.to_numeric(s.week,errors='coerce').dropna().astype(int).unique()):
    pred=predict_week(cur,prior,schedule,week,include_completed=True)
    profiles=build_waterfall_profiles(schedule,boxes,week)
    pmap={int(x['Game ID']):x for x in pred.to_dict('records') if pd.notna(x.get('Game ID'))}
    target=s[pd.to_numeric(s.week,errors='coerce').eq(week)]
    for _,g in target.iterrows():
        try: gid=int(g.game_id)
        except: continue
        p=pmap.get(gid); rec=profiles.get(str(gid),{})
        if p is None or rec.get('status')!='ok': continue
        conf=num(p.get('Confidence'))
        if conf is None or not (.75 <= conf < .80): continue
        side=str(p.get('Predicted Side','')).strip().lower()
        if side not in ('home','away'): continue
        other='away' if side=='home' else 'home'
        f,d=rec[side],rec[other]
        if not (f['def_run'] < d['off_run'] and f['margin'] >= d['margin']): continue
        hp=num(g.get('home_points')); ap=num(g.get('away_points'))
        if hp is None or ap is None: continue
        prefilter.append({
            'season':SEASON,'week':week,'game_id':gid,'home':g.home_team,'away':g.away_team,
            'predicted_side':side,'predicted_team':g[side+'_team'],'confidence':conf,
            'fav_def_ypc':f['def_run'],'dog_off_ypc':d['off_run'],
            'predicted_to_margin':f['margin'],'other_to_margin':d['margin'],
            'home_points':hp,'away_points':ap
        })

print('candidate games before odds gate',len(prefilter),flush=True)

quotes={}; errors=[]
with ThreadPoolExecutor(max_workers=16) as ex:
    futs={ex.submit(fetch_quote,x['game_id']):x for x in prefilter}
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
    if fav_ml is None or dog_ml is None or not (-600 <= fav_ml <= -280 and dog_ml > 0): continue
    margin=(r['home_points']-r['away_points']) if side=='home' else (r['away_points']-r['home_points'])
    win=margin>0
    ml_profit=(10*100/abs(fav_ml)) if win else -10
    spread=q.get(side+'_spread'); sp=q.get(side+'_spread_price')
    ats_margin=(margin+spread) if spread is not None else None
    ats='W' if ats_margin is not None and ats_margin>1e-9 else 'L' if ats_margin is not None and ats_margin<-1e-9 else 'P' if ats_margin is not None else 'Missing'
    ats_profit=None
    if ats in ('W','L','P') and sp not in (None,0):
        if ats=='P': ats_profit=0
        elif ats=='L': ats_profit=-10
        else: ats_profit=(10*100/abs(sp)) if sp<0 else (10*sp/100)
    x=dict(r)
    x.update(provider=q['provider'],favorite_ml=fav_ml,underdog_ml=dog_ml,
             favorite_spread=spread,spread_price=sp,margin=margin,win=win,
             ml_profit_10=ml_profit,ats_result=ats,ats_profit_10=ats_profit)
    rows.append(x)

out=pd.DataFrame(rows)
out.to_csv(OUT/'tier4_2023_candidate_games.csv',index=False)
pd.DataFrame(errors).to_csv(OUT/'fetch_errors.csv',index=False)

n=len(out); w=int(out.win.sum()) if n else 0; l=n-w
mlp=float(out.ml_profit_10.sum()) if n else 0
ats=out[out.ats_result.isin(['W','L','P'])] if n else out
aw=int((ats.ats_result=='W').sum()) if n else 0
al=int((ats.ats_result=='L').sum()) if n else 0
ap=int((ats.ats_result=='P').sum()) if n else 0
apx=ats[ats.ats_profit_10.notna()] if n else ats
atsp=float(apx.ats_profit_10.sum()) if len(apx) else None

summary={
  'definition':{
    'season':2023,
    'model_confidence':'75% to under 80%',
    'favorite_ml':'-600 through -280 inclusive',
    'run_defense':'favorite defensive YPC allowed < underdog offensive YPC',
    'turnovers':'favorite turnover margin/game >= underdog turnover margin/game',
    'market':'favorite moneyline'
  },
  'coverage':{'prefilter':len(prefilter),'quotes':len(quotes),'fetch_errors':len(errors),'qualifiers':n},
  'result':{
    'record':f'{w}-{l}','wins':w,'losses':l,'win_rate':w/n if n else None,
    'ml_profit_10':round(mlp,2),'ml_roi':mlp/(10*n) if n else None,
    'ats_record':f'{aw}-{al}-{ap}','ats_win_rate_ex_push':aw/(aw+al) if aw+al else None,
    'ats_profit_10':round(atsp,2) if atsp is not None else None,
    'ats_roi':atsp/(10*len(apx)) if atsp is not None and len(apx) else None
  },
  'games':out[['week','game_id','away','home','predicted_team','confidence','favorite_ml','favorite_spread','win','ats_result']].to_dict('records') if n else []
}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2),flush=True)
