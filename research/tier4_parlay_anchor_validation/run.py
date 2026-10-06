from pathlib import Path
import sys, json, math, time
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
OUT=Path(__file__).resolve().parent
OUT.mkdir(parents=True,exist_ok=True)

from model_v1_5 import predict_week
from matchup_advantages import build_waterfall_profiles, normalize_fbs_schedule, conference_group

SEASONS=(2024,2025,2026)
MAX_WEEK_2026=5

def csv_url(url):
    with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 tier4-validation'}),timeout=90) as r:
        return pd.read_csv(r,low_memory=False)

def fetch_json(url,tries=3,timeout=25):
    last=None
    for i in range(tries):
        try:
            with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0 tier4-validation'}),timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            last=e
            time.sleep(.35*(i+1))
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
    return dict(
        provider=str((o.get('provider') or {}).get('name') or '').strip(),
        home_ml=hm,away_ml=am,home_spread=hs,away_spread=as_,
        home_spread_price=hsp,away_spread_price=asp,details=o.get('details')
    )

def choose_2026(payload):
    opts=[parse_provider(x) for x in (payload.get('pickcenter') or [])]
    opts=[x for x in opts if x['home_ml'] is not None and x['away_ml'] is not None]
    if not opts:return None
    opts.sort(key=lambda x:0 if 'draftkings' in x['provider'].lower().replace(' ','') else 1)
    return opts[0]

def fetch_quote(item):
    season=item['season']; gid=item['game_id']
    try:
        if season<=2025:
            url=f'https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/events/{gid}/competitions/{gid}/odds/58?lang=en&region=us'
            q=parse_provider(fetch_json(url))
            if not q['provider']:q['provider']='ESPN BET'
        else:
            url=f'https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event={gid}'
            q=choose_2026(fetch_json(url))
            if q is None:return gid,None,'No paired 2026 moneyline'
        q['url']=url
        if q['home_ml'] is None or q['away_ml'] is None:
            return gid,None,'Missing paired moneyline'
        return gid,q,None
    except Exception as e:
        return gid,None,repr(e)

def completed_bool(series):
    return series.astype(str).str.lower().isin(['true','t','1','1.0','yes','y'])

schedules={}; boxes={}; summaries={}
for year in (2023,2024,2025,2026):
    summaries[year]=csv_url(
        f'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_{year}.csv'
    )
for year in SEASONS:
    schedules[year]=csv_url(f'https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{year}.csv')
    boxes[year]=csv_url(f'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_{year}.csv')

prefilter=[]
model_counts={}
for season in SEASONS:
    raw=schedules[season]
    s=normalize_fbs_schedule(raw).copy()
    s=s[s.season_type.astype(str).str.lower().eq('regular')]
    if season==2026:
        s=s[pd.to_numeric(s.week,errors='coerce').le(MAX_WEEK_2026)]
    weeks=sorted(pd.to_numeric(s.week,errors='coerce').dropna().astype(int).unique())
    model_counts[str(season)]={}
    for week in weeks:
        pred=predict_week(summaries[season],summaries[season-1],raw,week,include_completed=True)
        profiles=build_waterfall_profiles(raw,boxes[season],week)
        target=s[pd.to_numeric(s.week,errors='coerce').eq(week)].copy()
        pmap={int(x['Game ID']):x for x in pred.to_dict('records') if pd.notna(x.get('Game ID'))}
        model_counts[str(season)][str(week)]=len(pmap)
        for _,g in target.iterrows():
            try:gid=int(g.game_id)
            except:continue
            p=pmap.get(gid); rec=profiles.get(str(gid),{})
            if p is None or rec.get('status')!='ok':continue
            try:conf=float(p.get('Confidence'))
            except:continue
            if not math.isfinite(conf) or conf<.70 or conf>1:continue
            side=str(p.get('Predicted Side','')).strip().lower()
            if side not in ('home','away'):continue
            other='away' if side=='home' else 'home'
            f=rec[side]; d=rec[other]
            if not all(math.isfinite(float(x)) for x in (f['def_run'],d['off_run'],f['margin'],d['margin'])):continue
            # These are the Tier 4 football/model gates before the market-price gate.
            if not (f['def_run'] < d['off_run'] and f['margin'] >= d['margin']):continue
            hp=num(g.get('home_points'));ap=num(g.get('away_points'))
            if hp is None or ap is None:continue
            hg=conference_group(g.get('home_conference'),g.get('home_team'))
            ag=conference_group(g.get('away_conference'),g.get('away_team'))
            group='P4/P4' if hg=='P4' and ag=='P4' else 'G6/G6' if hg=='G6' and ag=='G6' else 'Mixed/Other'
            prefilter.append({
                'season':season,'week':week,'game_id':gid,
                'home':g.home_team,'away':g.away_team,
                'predicted_side':side,'predicted_team':g[side+'_team'],
                'confidence':conf,'group':group,'neutral_site':bool(g.get('neutral_site',False)),
                'fav_def_ypc_if_market_agrees':f['def_run'],
                'dog_off_ypc_if_market_agrees':d['off_run'],
                'predicted_to_margin':f['margin'],'other_to_margin':d['margin'],
                'turnover_edge':f['margin']-d['margin'],
                'home_points':hp,'away_points':ap,'start_date':g.get('start_date')
            })

print('prefilter after model + football gates',len(prefilter),flush=True)

quotes={};errors=[]
with ThreadPoolExecutor(max_workers=24) as ex:
    futs={ex.submit(fetch_quote,x):x for x in prefilter}
    for f in as_completed(futs):
        gid,q,e=f.result()
        if q is not None:quotes[gid]=q
        else:errors.append({'game_id':gid,'error':e})

rows=[]
for r in prefilter:
    q=quotes.get(r['game_id'])
    if not q:continue
    side=r['predicted_side'];other='away' if side=='home' else 'home'
    fav_ml=q[side+'_ml'];dog_ml=q[other+'_ml']
    # Model-selected team must actually be the market favorite, at the production price.
    if fav_ml is None or dog_ml is None or not (-600<=fav_ml<=-280 and dog_ml>0):
        continue
    margin=(r['home_points']-r['away_points']) if side=='home' else (r['away_points']-r['home_points'])
    win=margin>0
    ml_profit=(10*100/abs(fav_ml)) if win else -10
    implied=abs(fav_ml)/(abs(fav_ml)+100)
    spread=q.get(side+'_spread');spread_price=q.get(side+'_spread_price')
    ats_margin=(margin+spread) if spread is not None else None
    ats='W' if ats_margin is not None and ats_margin>1e-9 else 'L' if ats_margin is not None and ats_margin<-1e-9 else 'P' if ats_margin is not None else 'Missing'
    ats_profit=None
    if ats in ('W','L','P') and spread_price not in (None,0):
        if ats=='P':ats_profit=0.0
        elif ats=='L':ats_profit=-10.0
        else:ats_profit=(10*100/abs(spread_price)) if spread_price<0 else (10*spread_price/100)
    x=dict(r)
    x.update(provider=q['provider'],source_url=q['url'],favorite_ml=fav_ml,underdog_ml=dog_ml,
             favorite_spread=spread,spread_price=spread_price,market_details=q.get('details'),
             margin=margin,win=win,implied_probability=implied,ml_profit_10=ml_profit,
             ats_margin=ats_margin,ats_result=ats,ats_profit_10=ats_profit,
             favorite_venue='Home' if side=='home' else 'Road')
    rows.append(x)

out=pd.DataFrame(rows)
out.to_csv(OUT/'tier4_parlay_anchor_games.csv',index=False)
pd.DataFrame(prefilter).to_csv(OUT/'prefilter_candidates.csv',index=False)
pd.DataFrame(errors).to_csv(OUT/'fetch_errors.csv',index=False)

def stat(frame):
    n=len(frame)
    if not n:
        return {'games':0,'wins':0,'losses':0,'win_rate':None,'ml_profit_10':0,'ml_roi':None,
                'mean_implied_probability':None,'expected_wins':None,'actual_minus_expected':None,
                'ats_graded':0,'ats_w':0,'ats_l':0,'ats_p':0,'ats_win_rate_ex_push':None,
                'ats_profit_10':None,'ats_roi':None}
    w=int(frame.win.sum());l=n-w
    mlp=float(frame.ml_profit_10.sum())
    exp=float(frame.implied_probability.sum())
    ats=frame[frame.ats_result.isin(['W','L','P'])]
    aw=int((ats.ats_result=='W').sum());al=int((ats.ats_result=='L').sum());ap=int((ats.ats_result=='P').sum())
    apx=ats[ats.ats_profit_10.notna()]
    atsp=float(apx.ats_profit_10.sum()) if len(apx) else None
    return {
        'games':n,'wins':w,'losses':l,'win_rate':w/n,
        'ml_profit_10':round(mlp,2),'ml_roi':mlp/(10*n),
        'mean_implied_probability':float(frame.implied_probability.mean()),
        'expected_wins':exp,'actual_minus_expected':w-exp,
        'avg_favorite_ml':float(frame.favorite_ml.mean()),
        'avg_confidence':float(frame.confidence.mean()),
        'ats_graded':len(ats),'ats_w':aw,'ats_l':al,'ats_p':ap,
        'ats_win_rate_ex_push':aw/(aw+al) if aw+al else None,
        'ats_profit_10':round(atsp,2) if atsp is not None else None,
        'ats_roi':atsp/(10*len(apx)) if atsp is not None and len(apx) else None,
    }

report={
    'definition':{
        'favorite_ml':'-600 through -280 inclusive',
        'model':'core model selects favorite at >=70% confidence',
        'run_defense':'favorite defensive YPC allowed < underdog offensive YPC',
        'turnovers':'favorite turnover margin/game >= underdog turnover margin/game',
        'history':'earlier current-season FBS games only',
        'seasons':'2024-2025 regular seasons; 2026 through Week 5',
        'odds':'2024-2025 ESPN BET archive; 2026 DraftKings preferred from ESPN summary',
    },
    'coverage':{
        'model_football_prefilter':len(prefilter),'quotes_retrieved':len(quotes),'fetch_errors':len(errors),
        'tier4_games':len(out),'model_counts':model_counts
    },
    'overall':stat(out),
    'by_season':{},'price_buckets':{},'confidence_buckets':{},'by_group':{},'by_venue':{},
    'turnover_strictness':{}
}
if not out.empty:
    for y,g in out.groupby('season'):report['by_season'][str(int(y))]=stat(g)
    for name,lo,hi in [('-280_to_-349',-349,-280),('-350_to_-449',-449,-350),('-450_to_-600',-600,-450)]:
        report['price_buckets'][name]=stat(out[out.favorite_ml.between(lo,hi)])
    for name,lo,hi in [('70_to_74',.70,.749999),('75_to_79',.75,.799999),('80_plus',.80,1.0)]:
        report['confidence_buckets'][name]=stat(out[out.confidence.between(lo,hi)])
    for grp,g in out.groupby('group'):report['by_group'][str(grp)]=stat(g)
    for v,g in out.groupby('favorite_venue'):report['by_venue'][str(v)]=stat(g)
    report['turnover_strictness']['equal_or_better']=stat(out)
    report['turnover_strictness']['strictly_better']=stat(out[out.turnover_edge>1e-10])
    report['turnover_strictness']['edge_at_least_0_5']=stat(out[out.turnover_edge>=.5-1e-10])
    report['turnover_strictness']['edge_at_least_1_0']=stat(out[out.turnover_edge>=1.0-1e-10])

(OUT/'summary.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2),flush=True)
