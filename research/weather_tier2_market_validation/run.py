from pathlib import Path
from urllib.request import urlopen, Request
import json, time
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'research/weather_ypc_validation/game_details_hfa_turnover.csv'
OUT=Path(__file__).resolve().parent
OUT.mkdir(parents=True,exist_ok=True)

df=pd.read_csv(SRC,low_memory=False)
inc=df['inclement'].astype(str).str.lower().eq('true')
cand=df[inc & df['home_def_to_pick'].eq('home')].copy()
assert len(cand)==29, f'Expected 29 candidates, found {len(cand)}'

def get_json(url,tries=3):
    last=None
    for i in range(tries):
        try:
            req=Request(url,headers={'User-Agent':'Mozilla/5.0 weather-tier2-market-research'})
            with urlopen(req,timeout=30) as r:return json.load(r)
        except Exception as e:
            last=e; time.sleep(1+i)
    raise last

def num(v):
    if v is None:return None
    try:
        s=str(v).strip().replace('+','').replace('−','-')
        if not s or s.lower() in ('nan','none','null'):return None
        return float(s)
    except:return None

def parse_provider(o):
    name=str((o.get('provider') or {}).get('name') or o.get('providerName') or '').strip()
    ml=(o.get('moneyline') or {}).get('home',{})
    home_ml=num((ml.get('close') or {}).get('odds'))
    if home_ml is None: home_ml=num((o.get('homeTeamOdds') or {}).get('moneyLine'))
    ps=(o.get('pointSpread') or {}).get('home',{})
    home_spread=num((ps.get('close') or {}).get('line'))
    spread_price=num((ps.get('close') or {}).get('odds'))
    legacy_home=o.get('homeTeamOdds') or {}
    raw_spread=num(o.get('spread'))
    if home_spread is None and raw_spread is not None:
        mag=abs(raw_spread)
        if legacy_home.get('favorite') is True: home_spread=-mag
        elif legacy_home.get('underdog') is True: home_spread=mag
        else:
            details=str(o.get('details') or '').strip()
            if details:
                last=num(details.split()[-1])
                if last is not None:
                    if legacy_home.get('favorite') is True: home_spread=last if last<0 else -abs(last)
                    elif legacy_home.get('underdog') is True: home_spread=abs(last)
    if spread_price is None:
        for k in ('spreadOdds','spreadPrice','odds'):
            spread_price=num(legacy_home.get(k))
            if spread_price is not None: break
    return {'provider':name,'home_ml':home_ml,'home_spread':home_spread,'spread_price':spread_price,'details':o.get('details')}

def choose_quote(p):
    opts=[]
    for o in (p.get('pickcenter') or []):
        q=parse_provider(o)
        if q['home_ml'] is not None or q['home_spread'] is not None: opts.append(q)
    for o in (p.get('odds') or []):
        q=parse_provider(o)
        if q['home_ml'] is not None or q['home_spread'] is not None: opts.append(q)
    if not opts:return None
    def rank(q):
        n=q['provider'].lower().replace(' ','')
        if 'draftkings' in n:return 0
        if 'espnbet' in n:return 1
        if q['home_ml'] is not None and q['home_spread'] is not None:return 2
        return 3
    return sorted(opts,key=rank)[0]

rows=[]; errors=[]
for rec in cand.to_dict('records'):
    gid=int(rec['game_id']); season=int(rec['season'])
    q=None; errs=[]
    # 2024-2025: prefer the archived ESPN BET closing record used in our earlier historical pricing work.
    if season<=2025:
        archive='https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/events/'+str(gid)+'/competitions/'+str(gid)+'/odds/58?lang=en&region=us'
        try:
            aq=parse_provider(get_json(archive))
            if aq['home_ml'] is not None or aq['home_spread'] is not None: q=aq
        except Exception as e: errs.append('archive58:'+repr(e))
    # Fallback / 2026 source: historical event summary, preferring DraftKings when present.
    if q is None or q['home_ml'] is None or q['home_spread'] is None:
        url='https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event='+str(gid)
        try:
            sq=choose_quote(get_json(url))
            if sq is not None:
                if q is None: q=sq
                else:
                    for key in ('home_ml','home_spread','spread_price','details'):
                        if q.get(key) is None and sq.get(key) is not None: q[key]=sq[key]
                    if not q.get('provider'): q['provider']=sq.get('provider')
        except Exception as e: errs.append('summary:'+repr(e))
    if errs and q is None: errors.append({'game_id':gid,'error':' | '.join(errs)})
    hp=float(rec['home_points']); ap=float(rec['away_points']); margin=hp-ap; win=margin>0
    home_ml=q['home_ml'] if q else None
    spread=q['home_spread'] if q else None
    spread_price=q['spread_price'] if q else None
    ml_profit=None
    if home_ml is not None and home_ml!=0:
        ml_profit=((10*100/abs(home_ml)) if home_ml<0 else (10*home_ml/100)) if win else -10
    ats_margin=(margin+spread) if spread is not None else None
    ats_result='W' if ats_margin is not None and ats_margin>1e-9 else 'L' if ats_margin is not None and ats_margin<-1e-9 else 'P' if ats_margin is not None else 'Missing'
    ats_profit=None
    if ats_result in ('W','L','P') and spread_price is not None and spread_price!=0:
        if ats_result=='P': ats_profit=0.0
        elif ats_result=='L': ats_profit=-10.0
        else: ats_profit=(10*100/abs(spread_price)) if spread_price<0 else (10*spread_price/100)
    out=dict(rec)
    out.update({'provider':q['provider'] if q else None,'market_details':q['details'] if q else None,
                'home_ml':home_ml,'home_spread':spread,'home_spread_price':spread_price,
                'home_margin':margin,'su_win':win,'ml_profit_10':ml_profit,
                'ats_margin':ats_margin,'ats_result':ats_result,'ats_profit_10':ats_profit})
    rows.append(out)
    time.sleep(.03)

out=pd.DataFrame(rows)
out.to_csv(OUT/'weather_tier2_market_games.csv',index=False)
pd.DataFrame(errors).to_csv(OUT/'weather_tier2_market_errors.csv',index=False)

def record(frame):
    n=len(frame); w=int(frame.su_win.sum())
    priced=frame[frame.home_ml.notna()]
    profit=float(priced.ml_profit_10.sum()) if len(priced) else None
    risk=10*len(priced)
    ats=frame[frame.ats_result.isin(['W','L','P'])]
    aw=int((ats.ats_result=='W').sum()); al=int((ats.ats_result=='L').sum()); ap=int((ats.ats_result=='P').sum())
    ats_priced=ats[ats.ats_profit_10.notna()]
    ats_profit=float(ats_priced.ats_profit_10.sum()) if len(ats_priced) else None
    return {'games':n,'wins':w,'losses':n-w,'win_rate':w/n if n else None,
            'ml_priced':len(priced),'ml_profit_10':round(profit,2) if profit is not None else None,
            'ml_roi':profit/risk if profit is not None and risk else None,
            'avg_ml':float(priced.home_ml.mean()) if len(priced) else None,'median_ml':float(priced.home_ml.median()) if len(priced) else None,
            'ats_graded':len(ats),'ats_w':aw,'ats_l':al,'ats_p':ap,'ats_win_rate_ex_push':aw/(aw+al) if aw+al else None,
            'ats_priced':len(ats_priced),'ats_profit_10':round(ats_profit,2) if ats_profit is not None else None,
            'ats_roi':ats_profit/(10*len(ats_priced)) if ats_profit is not None and len(ats_priced) else None}

summary={'overall':record(out),'by_season':{},'by_group':{},'ml_price_buckets':{},'spread_buckets':{}}
for y,g in out.groupby('season'): summary['by_season'][str(int(y))]=record(g)
for grp,g in out.groupby('group'): summary['by_group'][str(grp)]=record(g)

buckets=[
 ('Underdog_or_pickem',lambda x:x>=100),
 ('Fav_-110_to_-199',lambda x:(x<=-110)&(x>=-199)),
 ('Fav_-200_to_-299',lambda x:(x<=-200)&(x>=-299)),
 ('Fav_-300_to_-499',lambda x:(x<=-300)&(x>=-499)),
 ('Fav_-500_or_shorter',lambda x:x<=-500)]
for name,fn in buckets:
    g=out[out.home_ml.notna() & fn(out.home_ml)]
    summary['ml_price_buckets'][name]=record(g)

spread_buckets=[
 ('Dog_or_pickem',lambda x:x>=0),
 ('Fav_0.5_to_3.5',lambda x:(x<0)&(x>=-3.5)),
 ('Fav_4_to_7.5',lambda x:(x<=-4)&(x>=-7.5)),
 ('Fav_8_to_13.5',lambda x:(x<=-8)&(x>=-13.5)),
 ('Fav_14_plus',lambda x:x<=-14)]
for name,fn in spread_buckets:
    g=out[out.home_spread.notna() & fn(out.home_spread)]
    summary['spread_buckets'][name]=record(g)

priced=out[out.home_ml.notna()].copy()
def implied(ml): return (-ml)/((-ml)+100) if ml<0 else 100/(ml+100)
summary['overall']['sum_implied_wins']=float(priced.home_ml.map(implied).sum()) if len(priced) else None
summary['overall']['mean_implied_prob']=float(priced.home_ml.map(implied).mean()) if len(priced) else None
(OUT/'weather_tier2_market_summary.json').write_text(json.dumps(summary,indent=2))

def fmt_rec(s): return f"{s['wins']}–{s['losses']} ({s['win_rate']:.1%})" if s['games'] else '—'
lines=['# Weather Tier 2 market validation','',
 'Frozen rule: outdoor inclement-weather game; non-neutral home team; home team enters with lower defensive rushing YPC allowed and better turnover margin/game than the opponent. No odds or spread threshold is used to select the 29 games.','',
 '## Overall','',f"- SU: {fmt_rec(summary['overall'])}."]
if summary['overall']['ml_roi'] is not None:
    lines.append(f"- ML priced: {summary['overall']['ml_priced']}/{summary['overall']['games']}; flat $10-risk profit ${summary['overall']['ml_profit_10']:+.2f}; ROI {summary['overall']['ml_roi']:.1%}.")
if summary['overall']['ats_graded']:
    lines.append(f"- ATS: {summary['overall']['ats_w']}–{summary['overall']['ats_l']}–{summary['overall']['ats_p']} across {summary['overall']['ats_graded']} graded games ({summary['overall']['ats_win_rate_ex_push']:.1%} excluding pushes).")
lines += ['','## Moneyline price buckets','','| Bucket | Games | SU | ML ROI | ATS |','|---|---:|---:|---:|---:|']
for name,s in summary['ml_price_buckets'].items():
    ats=f"{s['ats_w']}–{s['ats_l']}–{s['ats_p']}" if s['ats_graded'] else '—'
    roi='—' if s['ml_roi'] is None else f"{s['ml_roi']:.1%}"
    lines.append(f"| {name} | {s['games']} | {fmt_rec(s)} | {roi} | {ats} |")
lines += ['','## Season splits','','| Season | SU | ML ROI | ATS |','|---|---:|---:|---:|']
for y,s in summary['by_season'].items():
    ats=f"{s['ats_w']}–{s['ats_l']}–{s['ats_p']}" if s['ats_graded'] else '—'
    roi='—' if s['ml_roi'] is None else f"{s['ml_roi']:.1%}"
    lines.append(f"| {y} | {fmt_rec(s)} | {roi} | {ats} |")
lines += ['','Every candidate and archived quote is in weather_tier2_market_games.csv.']
(OUT/'WEATHER_TIER2_MARKET.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(summary,indent=2))