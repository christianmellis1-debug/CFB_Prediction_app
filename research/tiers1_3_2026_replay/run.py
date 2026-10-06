from pathlib import Path
from urllib.request import Request, urlopen
import json, math, time
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
OUT.mkdir(parents=True,exist_ok=True)

t1=pd.read_csv(ROOT/'research/six_advantage_odds_2026_week5/moneylines.csv')

def fetch_json(url):
    req=Request(url,headers={'User-Agent':'Mozilla/5.0 retrospective'})
    with urlopen(req,timeout=30) as r:
        return json.load(r)

def num(v):
    try:
        s=str(v).strip().replace('+','').replace('−','-')
        x=float(s)
        return x if math.isfinite(x) else None
    except:
        return None

def home_spread_from(o):
    ps=(o.get('pointSpread') or {}).get('home',{})
    close=(ps.get('close') or {})
    line=num(close.get('line'))
    price=num(close.get('odds'))
    if line is None:
        h=o.get('homeTeamOdds') or {}
        raw=num(o.get('spread'))
        if raw is not None:
            if h.get('favorite') is True: line=-abs(raw)
            elif h.get('underdog') is True: line=abs(raw)
        if price is None: price=num(h.get('spreadOdds'))
    return line,price

def parse_summary(gid):
    payload=fetch_json(f'https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event={gid}')
    opts=[]
    for o in payload.get('pickcenter',[]) or []:
        name=str((o.get('provider') or {}).get('name') or '').strip()
        line,price=home_spread_from(o)
        if line is not None:
            opts.append((0 if 'draftkings' in name.lower().replace(' ','') else 1,name,line,price,o.get('details')))
    if not opts:
        return None
    opts.sort()
    _,name,line,price,details=opts[0]
    return dict(provider=name,home_spread=line,spread_price=price,details=details)

sched=pd.read_csv('https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_2026.csv',low_memory=False)
sched['game_id']=pd.to_numeric(sched.game_id,errors='coerce')

rows=[]
for rec in t1.to_dict('records'):
    gid=int(rec['game_id'])
    g=sched[sched.game_id.eq(gid)]
    if len(g)!=1:
        raise RuntimeError(f'schedule missing {gid}')
    g=g.iloc[0]
    q=parse_summary(gid)
    if q is None:
        raise RuntimeError(f'no spread {gid}')
    hp=num(g.get('home_points')); ap=num(g.get('away_points'))
    margin=hp-ap
    ats_margin=margin+q['home_spread']
    ats='W' if ats_margin>1e-9 else 'L' if ats_margin<-1e-9 else 'P'
    rows.append({
        'tier':1,'season':2026,'week':int(rec['week']),'game_id':gid,
        'away':g['away_team'],'home':g['home_team'],'pick':g['home_team'],
        'market':'ATS','line':q['home_spread'],'price':q['spread_price'],
        'provider':q['provider'],'final':f'{int(hp)}-{int(ap)}','ats_margin':ats_margin,'result':ats,
        'source_sample':'exact 6/6'
    })
    time.sleep(.05)

# Tier 2 current-rule 2026 historical candidates from the completed research set.
t2_candidates=[
    dict(week=3,game_id=401858225,away='Syracuse',home='Pittsburgh',line=-10.5,result='W',final='27-13'),
    dict(week=4,game_id=401862779,away='Army',home='Temple',line=4.0,result='P',final='17-21'),
    dict(week=5,game_id=401856710,away='Auburn',home='Tennessee',line=-6.0,result='W',final='24-14'),
    dict(week=5,game_id=401869932,away='Arkansas State',home='Louisiana',line=-4.5,result='L',final='23-20'),
]
tier1_ids={r['game_id'] for r in rows}
for x in t2_candidates:
    x.update(tier=2,season=2026,pick=x['home'],market='ATS',price=None,provider='research archive',
             source_sample='weather defensive edge')
    x['suppressed_by_higher_tier']=x['game_id'] in tier1_ids
    rows.append(x)

# Tier 3 current rule: only 2026-through-W5 strong-turnover qualifier.
t3=dict(tier=3,season=2026,week=5,game_id=401856709,away='Kentucky',home='South Carolina',
        pick='Kentucky',market='ML',line=110,price=110,provider='DraftKings',final='35-34',
        result='W',source_sample='P4 turnover edge >= +1.0',suppressed_by_higher_tier=False)
rows.append(t3)

df=pd.DataFrame(rows)
if 'suppressed_by_higher_tier' not in df: df['suppressed_by_higher_tier']=False
df['suppressed_by_higher_tier']=df['suppressed_by_higher_tier'].fillna(False)

# Waterfall: Tier 1 always first. Tier 2 historical overlaps are suppressed. Tier 3 doesn't overlap.
published=df[~df.suppressed_by_higher_tier].copy()
published=published.sort_values(['week','tier','game_id'])
published.to_csv(OUT/'published_picks.csv',index=False)
df.to_csv(OUT/'all_candidates.csv',index=False)

def summarize(g):
    w=int((g.result=='W').sum()); l=int((g.result=='L').sum()); p=int((g.result=='P').sum())
    return {'picks':len(g),'wins':w,'losses':l,'pushes':p,'win_rate_ex_push':w/(w+l) if w+l else None}

summary={
    'overall':summarize(published),
    'by_tier':{str(int(t)):summarize(g) for t,g in published.groupby('tier')},
    'by_week':{str(int(w)):summarize(g) for w,g in published.groupby('week')},
    'candidate_counts_before_priority':{str(int(t)):len(g) for t,g in df.groupby('tier')},
    'suppressed_overlaps':df[df.suppressed_by_higher_tier][['tier','week','game_id','away','home','pick','market','line','result']].to_dict('records')
}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2))
print(published.to_string(index=False))
print(json.dumps(summary,indent=2))
