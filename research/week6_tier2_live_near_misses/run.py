from pathlib import Path
import json, time
from urllib.request import urlopen, Request
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
src=json.loads((ROOT/'research/week6_tier2_near_misses/near_misses.json').read_text()) if (ROOT/'research/week6_tier2_near_misses/near_misses.json').exists() else []
if not src:
    raise SystemExit('near_misses.json missing')

def get(url):
    req=Request(url,headers={'User-Agent':'Mozilla/5.0'})
    with urlopen(req,timeout=25) as r:return json.load(r)

def num(v):
    try:return float(str(v).replace('+','').replace('−','-'))
    except:return None

def parse(payload):
    qs=[]
    for o in payload.get('pickcenter',[]) or []:
        name=str((o.get('provider') or {}).get('name') or '').strip()
        ps=(o.get('pointSpread') or {}).get('home',{})
        line=num((ps.get('close') or {}).get('line'))
        price=num((ps.get('close') or {}).get('odds'))
        if line is None:
            legacy=o.get('homeTeamOdds') or {}
            raw=num(o.get('spread'))
            if raw is not None:
                if legacy.get('favorite') is True: line=-abs(raw)
                elif legacy.get('underdog') is True: line=abs(raw)
        if line is not None: qs.append((name,line,price))
    if not qs:return None
    qs.sort(key=lambda x:0 if 'draftkings' in x[0].lower().replace(' ','') else 1)
    return qs[0]

for r in src:
    gid=str(r['game_id'])
    try:q=parse(get('https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event='+gid))
    except Exception:q=None
    if q:
        r['live_spread_source']=q[0]; r['live_home_spread']=q[1]; r['live_spread_odds']=q[2]; r['spread_gate']=q[1]>-14
    else:
        r['live_spread_source']=None; r['live_home_spread']=None; r['live_spread_odds']=None
    r['missing_for_tier2']=[]
    if r['live_home_spread'] is None: r['missing_for_tier2'].append('current spread')
    elif r['live_home_spread']<=-14: r['missing_for_tier2'].append('spread must improve above -14')
    if not r.get('inclement'): r['missing_for_tier2'].append('inclement-weather forecast')
    r['qualifies_now']=not r['missing_for_tier2']
    time.sleep(.03)

(ROOT/'research/week6_tier2_live_near_misses').mkdir(exist_ok=True)
(ROOT/'research/week6_tier2_live_near_misses/live_near_misses.json').write_text(json.dumps(src,indent=2))
print(json.dumps(src,indent=2))
# rerun after shortlist sync
