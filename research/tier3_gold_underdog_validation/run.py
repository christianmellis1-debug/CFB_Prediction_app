from pathlib import Path
import sys
from urllib.request import urlopen, Request
from concurrent.futures import ThreadPoolExecutor, as_completed
import json, math, time
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from matchup_advantages import build_waterfall_profiles, normalize_fbs_schedule, conference_group
OUT=Path(__file__).resolve().parent
OUT.mkdir(parents=True,exist_ok=True)

SEASONS=(2024,2025,2026)
MAX_WEEK_2026=5

def fetch_json(url, tries=3, timeout=25):
    last=None
    for i in range(tries):
        try:
            req=Request(url,headers={'User-Agent':'Mozilla/5.0 tier3-validation'})
            with urlopen(req,timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            last=e
            time.sleep(.5*(i+1))
    raise last

def num(v):
    if v is None:return None
    try:
        s=str(v).strip().replace('+','').replace('−','-')
        if not s or s.lower() in ('nan','none','null','unavailable'):return None
        x=float(s)
        return x if math.isfinite(x) else None
    except:return None

def quote_from_odds(o, side):
    ml=(o.get('moneyline') or {}).get(side,{})
    money=num((ml.get('close') or {}).get('odds'))
    if money is None:
        money=num((o.get(side+'TeamOdds') or {}).get('moneyLine'))

    ps=(o.get('pointSpread') or {}).get(side,{})
    spread=num((ps.get('close') or {}).get('line'))
    spread_price=num((ps.get('close') or {}).get('odds'))
    team_odds=o.get(side+'TeamOdds') or {}
    if spread is None:
        raw=num(o.get('spread'))
        if raw is not None:
            if team_odds.get('favorite') is True: spread=-abs(raw)
            elif team_odds.get('underdog') is True: spread=abs(raw)
    if spread_price is None:
        spread_price=num(team_odds.get('spreadOdds'))
    return money,spread,spread_price

def parse_provider(o):
    name=str((o.get('provider') or {}).get('name') or '').strip()
    hm,hs,hsp=quote_from_odds(o,'home')
    am,as_,asp=quote_from_odds(o,'away')
    return dict(provider=name,home_ml=hm,away_ml=am,home_spread=hs,away_spread=as_,
                home_spread_price=hsp,away_spread_price=asp,details=o.get('details'))

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
            if not q['provider']: q['provider']='ESPN BET'
            q['url']=url
        else:
            url=f'https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event={gid}'
            q=choose_2026(fetch_json(url))
            if q is None:
                return gid,None,'No 2026 DraftKings/summary moneyline'
            q['url']=url
        if q['home_ml'] is None or q['away_ml'] is None:
            return gid,None,'Missing paired moneyline'
        return gid,q,None
    except Exception as e:
        return gid,None,repr(e)

schedules={}
boxes={}
sweep_candidates=[]

for season in SEASONS:
    su=f'https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{season}.csv'
    bu=f'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_{season}.csv'
    schedules[season]=pd.read_csv(su,low_memory=False)
    boxes[season]=pd.read_csv(bu,low_memory=False)
    s=normalize_fbs_schedule(schedules[season]).copy()
    s=s[s.season_type.astype(str).str.lower().eq('regular')]
    if season==2026:
        s=s[pd.to_numeric(s.week,errors='coerce').le(MAX_WEEK_2026)]
    weeks=sorted(pd.to_numeric(s.week,errors='coerce').dropna().astype(int).unique())
    for week in weeks:
        profiles=build_waterfall_profiles(schedules[season],boxes[season],week)
        target=s[pd.to_numeric(s.week,errors='coerce').eq(week)]
        for _,g in target.iterrows():
            try: gid=int(g.game_id)
            except: continue
            rec=profiles.get(str(gid),{})
            if rec.get('status')!='ok':continue
            neutral=str(g.get('neutral_site','')).strip().lower() in ('true','t','1','1.0','yes','y')
            if neutral: continue
            h,a=rec['home'],rec['away']
            home_sweep=h['off_run']>a['off_run'] and h['def_run']<a['def_run'] and h['margin']>a['margin']
            away_sweep=a['off_run']>h['off_run'] and a['def_run']<h['def_run'] and a['margin']>h['margin']
            if home_sweep==away_sweep:continue
            side='home' if home_sweep else 'away'
            dog=rec[side]
            other=rec['away' if side=='home' else 'home']
            hg=conference_group(g.get('home_conference'),g.get('home_team'))
            ag=conference_group(g.get('away_conference'),g.get('away_team'))
            group='P4/P4' if hg=='P4' and ag=='P4' else 'G6/G6' if hg=='G6' and ag=='G6' else 'Mixed/Other'
            sweep_candidates.append({
                'season':season,'week':week,'game_id':gid,
                'home':g.home_team,'away':g.away_team,'sweep_side':side,
                'sweep_team':g[side+'_team'],'other_team':g[('away' if side=='home' else 'home')+'_team'],
                'group':group,'start_date':g.get('start_date'),
                'home_points':g.get('home_points'),'away_points':g.get('away_points'),
                'sweep_off_ypc':dog['off_run'],'other_off_ypc':other['off_run'],
                'sweep_def_ypc':dog['def_run'],'other_def_ypc':other['def_run'],
                'sweep_to_margin':dog['margin'],'other_to_margin':other['margin'],
                'sweep_games':dog['games'],'other_games':other['games'],
            })

print('metric-sweep candidates before odds',len(sweep_candidates),flush=True)

quotes={}; errors=[]
with ThreadPoolExecutor(max_workers=20) as ex:
    futures={ex.submit(fetch_quote,x):x for x in sweep_candidates}
    for f in as_completed(futures):
        gid,q,err=f.result()
        if q is not None:quotes[gid]=q
        else:errors.append({'game_id':gid,'error':err})

rows=[]
for rec in sweep_candidates:
    q=quotes.get(rec['game_id'])
    if not q:continue
    side=rec['sweep_side']; other='away' if side=='home' else 'home'
    dog_ml=q[side+'_ml']; fav_ml=q[other+'_ml']
    if dog_ml is None or fav_ml is None:continue
    is_dog=(100<=dog_ml<=170 and fav_ml<=-100)
    # Production requires the sweeping side to be the short underdog.
    if not is_dog:continue
    spread=q.get(side+'_spread')
    spread_price=q.get(side+'_spread_price')
    hp=num(rec['home_points']); ap=num(rec['away_points'])
    if hp is None or ap is None:continue
    margin=(hp-ap) if side=='home' else (ap-hp)
    win=margin>0
    ml_profit=(10*dog_ml/100) if win else -10
    ats_margin=margin+spread if spread is not None else None
    ats_result='W' if ats_margin is not None and ats_margin>1e-9 else 'L' if ats_margin is not None and ats_margin<-1e-9 else 'P' if ats_margin is not None else 'Missing'
    ats_profit=None
    if ats_result in ('W','L','P') and spread_price not in (None,0):
        if ats_result=='P':ats_profit=0.0
        elif ats_result=='L':ats_profit=-10.0
        else:ats_profit=(10*100/abs(spread_price)) if spread_price<0 else (10*spread_price/100)
    row=dict(rec)
    row.update(provider=q['provider'],source_url=q['url'],dog_ml=dog_ml,favorite_ml=fav_ml,
               dog_spread=spread,dog_spread_price=spread_price,win=win,margin=margin,
               ml_profit_10=ml_profit,ats_margin=ats_margin,ats_result=ats_result,ats_profit_10=ats_profit)
    rows.append(row)

out=pd.DataFrame(rows)
out.to_csv(OUT/'tier3_gold_underdog_games.csv',index=False)
pd.DataFrame(errors).to_csv(OUT/'fetch_errors.csv',index=False)

def stat(frame):
    n=len(frame); w=int(frame.win.sum()) if n else 0
    ats=frame[frame.ats_result.isin(['W','L','P'])] if n else frame
    aw=int((ats.ats_result=='W').sum()) if n else 0
    al=int((ats.ats_result=='L').sum()) if n else 0
    ap=int((ats.ats_result=='P').sum()) if n else 0
    apx=ats[ats.ats_profit_10.notna()] if n else ats
    ml_profit=float(frame.ml_profit_10.sum()) if n else 0.0
    ats_profit=float(apx.ats_profit_10.sum()) if len(apx) else None
    return {
        'games':n,'ml_w':w,'ml_l':n-w,'ml_win_rate':w/n if n else None,
        'ml_profit_10':round(ml_profit,2),'ml_roi':ml_profit/(10*n) if n else None,
        'avg_dog_ml':float(frame.dog_ml.mean()) if n else None,
        'ats_graded':len(ats),'ats_w':aw,'ats_l':al,'ats_p':ap,
        'ats_win_rate_ex_push':aw/(aw+al) if aw+al else None,
        'ats_profit_10':round(ats_profit,2) if ats_profit is not None else None,
        'ats_roi':ats_profit/(10*len(apx)) if ats_profit is not None and len(apx) else None,
    }

report={
    'definition':{
        'dog_moneyline':'+100 through +170',
        'neutral_site':'excluded',
        'metrics':'higher offensive YPC, lower defensive YPC allowed, better turnover margin/game',
        'history':'earlier current-season FBS games only',
        'seasons':'2024-2025 regular seasons; 2026 through Week 5',
        'odds':'2024-2025 ESPN BET archive; 2026 DraftKings preferred from ESPN summary'
    },
    'coverage':{
        'metric_sweep_candidates':len(sweep_candidates),
        'quotes_retrieved':len(quotes),
        'fetch_errors':len(errors),
        'tier3_games':len(out)
    },
    'overall':stat(out),
    'by_season':{},
    'by_group':{},
    'by_venue':{},
    'price_buckets':{},
}
if not out.empty:
    for y,g in out.groupby('season'):report['by_season'][str(int(y))]=stat(g)
    for grp,g in out.groupby('group'):report['by_group'][str(grp)]=stat(g)
    for side,g in out.groupby('sweep_side'):report['by_venue']['Home' if side=='home' else 'Road']=stat(g)
    buckets=[
        ('+100_to_+120',100,120),
        ('+125_to_+145',121,145),
        ('+150_to_+170',146,170),
    ]
    for name,lo,hi in buckets:report['price_buckets'][name]=stat(out[out.dog_ml.between(lo,hi)])

(OUT/'summary.json').write_text(json.dumps(report,indent=2))

def rec(s):
    return '—' if not s['games'] else f"{s['ml_w']}–{s['ml_l']} ({s['ml_win_rate']:.1%})"
lines=[
'# Tier 3 Gold Standard Underdog validation','',
'Exact production rule: non-neutral underdog priced +100 through +170 that has higher pregame offensive YPC, lower defensive YPC allowed, and better turnover margin/game than the favorite. Earlier current-season FBS history only.','',
'## Overall','',
f"- Moneyline: {rec(report['overall'])}; flat $10-risk ROI {report['overall']['ml_roi']:.1%}." if report['overall']['games'] else '- No qualifying games.',
f"- ATS: {report['overall']['ats_w']}–{report['overall']['ats_l']}–{report['overall']['ats_p']} ({report['overall']['ats_win_rate_ex_push']:.1%} excluding pushes)." if report['overall']['ats_graded'] else '- No ATS grades.',
'','## Season splits','','| Season | ML record | ML ROI | ATS |','|---|---:|---:|---:|'
]
for y,s in report['by_season'].items():
    ats=f"{s['ats_w']}–{s['ats_l']}–{s['ats_p']}" if s['ats_graded'] else '—'
    lines.append(f"| {y} | {rec(s)} | {s['ml_roi']:.1%} | {ats} |")
lines += ['','## Matchup groups','','| Group | ML record | ML ROI | ATS |','|---|---:|---:|---:|']
for grp,s in report['by_group'].items():
    ats=f"{s['ats_w']}–{s['ats_l']}–{s['ats_p']}" if s['ats_graded'] else '—'
    lines.append(f"| {grp} | {rec(s)} | {s['ml_roi']:.1%} | {ats} |")
lines += ['','## Price buckets','','| Price | ML record | ML ROI | ATS |','|---|---:|---:|---:|']
for name,s in report['price_buckets'].items():
    ats=f"{s['ats_w']}–{s['ats_l']}–{s['ats_p']}" if s['ats_graded'] else '—'
    roi='—' if s['ml_roi'] is None else f"{s['ml_roi']:.1%}"
    lines.append(f"| {name} | {rec(s)} | {roi} | {ats} |")
(OUT/'README.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(report,indent=2),flush=True)
