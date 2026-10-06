from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor, as_completed
import json, math, time, sys
import pandas as pd
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from matchup_advantages import normalize_fbs_schedule, conference_group

OUT=Path(__file__).resolve().parent
SEASONS=[2024,2025,2026]
THUNDER={95,96,99}

def get_json(base,params=None,tries=2,timeout=25):
    url=base+('?' + urlencode(params,doseq=True) if params else '')
    last=None
    for attempt in range(tries):
        try:
            req=Request(url,headers={'User-Agent':'Mozilla/5.0 weather-ypc-research'})
            with urlopen(req,timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            last=e; time.sleep(.5*(attempt+1))
    raise last

def truthy(series):
    return series.astype(str).str.lower().isin(['true','t','1','1.0','yes','y'])

print('loading schedules', flush=True)
schedules={}; target_parts=[]
for season in SEASONS:
    s=pd.read_csv(f'https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{season}.csv',low_memory=False)
    schedules[season]=s
    n=normalize_fbs_schedule(s)
    mask=n.season_type.astype(str).str.lower().eq('regular') & truthy(n.completed)
    if season==2026:
        mask &= pd.to_numeric(n.week,errors='coerce').le(5)
    t=n[mask].copy()
    t['season']=season
    target_parts.append(t)
target=pd.concat(target_parts,ignore_index=True)
target['game_id']=pd.to_numeric(target.game_id,errors='coerce').astype('Int64')
target['start']=pd.to_datetime(target.start_date,utc=True,errors='coerce')
target=target.dropna(subset=['game_id','start'])
target['game_date_utc']=target.start.dt.date.astype(str)
print('target games',len(target),flush=True)

# Fast exact-equivalent rushing histories: only earlier weeks, current season, FBS-vs-FBS.
print('building pregame rushing profiles',flush=True)
profiles={}
for season in SEASONS:
    s=normalize_fbs_schedule(schedules[season]).copy()
    for col in ('season','week','game_id','home_id','away_id'):
        s[col]=pd.to_numeric(s[col],errors='coerce')
    s=s.dropna(subset=['week','game_id','home_id','away_id'])
    completed=truthy(s.completed)

    boxes=pd.read_csv(f'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_{season}.csv',low_memory=False)
    cols=['game_id','team_id','rushingYards','rushingAttempts','turnovers','fumblesLost','interceptions']
    b=boxes[cols].apply(pd.to_numeric,errors='coerce')
    valid=np.isfinite(b).all(axis=1) & ~b.duplicated(['game_id','team_id'],keep=False)
    valid &= b.rushingAttempts.gt(0) & b.rushingAttempts.mod(1).eq(0)
    to=b[['turnovers','fumblesLost','interceptions']]
    valid &= to.ge(0).all(axis=1) & to.mod(1).eq(0).all(axis=1)
    valid &= b.turnovers.eq(b.fumblesLost+b.interceptions)
    lookup=b[valid].set_index(['game_id','team_id'])

    totals={}  # tid -> [own yards, own att, opp yards, opp att, games, own TO, opp TO]
    history_ok={}
    target_ids=set(target.loc[target.season.eq(season),'game_id'].astype(int))
    max_week=5 if season==2026 else int(pd.to_numeric(s.week,errors='coerce').max())

    for week in range(0,max_week+1):
        # Score target games using only cumulative history from prior weeks.
        for _,g in s[s.week.eq(week) & s.game_id.isin(target_ids)].iterrows():
            gid=str(int(g.game_id)); rec={'status':'missing','reason':'Incomplete earlier-week FBS history.'}
            side_profiles={}
            for side in ('home','away'):
                tid=int(g[side+'_id'])
                t=totals.get(tid)
                if history_ok.get(tid,True) and t and t[4]>0 and t[1]>0 and t[3]>0:
                    side_profiles[side]={'off_run':t[0]/t[1],'def_run':t[2]/t[3],'games':t[4],
                                           'margin':(t[6]-t[5])/t[4]}
            if len(side_profiles)==2:
                rec.update(status='ok',reason='',**side_profiles)
            profiles[gid]=rec

        # Add all completed FBS games in this week for future weeks.
        for _,g in s[s.week.eq(week) & completed].iterrows():
            hid,aid=int(g.home_id),int(g.away_id); gid=int(g.game_id)
            keys=[(gid,hid),(gid,aid)]
            if not all(k in lookup.index for k in keys):
                history_ok[hid]=False; history_ok[aid]=False
                continue
            h,a=lookup.loc[keys[0]],lookup.loc[keys[1]]
            for tid,own,opp in [(hid,h,a),(aid,a,h)]:
                t=totals.setdefault(tid,[0.,0.,0.,0.,0,0.,0.])
                t[0]+=float(own.rushingYards); t[1]+=float(own.rushingAttempts)
                t[2]+=float(opp.rushingYards); t[3]+=float(opp.rushingAttempts); t[4]+=1
                t[5]+=float(own.turnovers); t[6]+=float(opp.turnovers)
    print('profiles season',season,'done',flush=True)

# Venue metadata.
venue_ids=sorted({str(int(v)) for v in pd.to_numeric(target.venue_id,errors='coerce').dropna().unique()})
def fetch_venue(vid):
    try:
        p=get_json(f'https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/venues/{vid}',{'lang':'en','region':'us'},timeout=15)
        return vid,p
    except Exception as e:
        return vid,{'_error':repr(e)}
venues={}
with ThreadPoolExecutor(max_workers=24) as ex:
    for f in as_completed([ex.submit(fetch_venue,v) for v in venue_ids]):
        vid,p=f.result();venues[vid]=p
print('venues',len(venues),'loaded',flush=True)

def addr_key(v):
    a=v.get('address') or {}
    city=str(a.get('city') or '').strip(); state=str(a.get('state') or '').strip(); country=str(a.get('country') or '').strip()
    return '|'.join([city,state,country]) if city else ''

addr_to_sample={}
for vid,v in venues.items():
    if v.get('indoor') is False and addr_key(v):
        addr_to_sample.setdefault(addr_key(v),v)

def geocode(item):
    key,v=item; city,state,country=key.split('|')
    a=v.get('address') or {}
    queries=[]
    q=', '.join([x for x in [city,state if country in ('USA','United States','US') else country] if x])
    queries.append((q,'US' if country in ('USA','United States','US') else None))
    if a.get('zipCode'): queries.append((str(a['zipCode']),'US' if country in ('USA','United States','US') else None))
    for name,cc in queries:
        try:
            params={'name':name,'count':5,'format':'json','language':'en'}
            if cc:params['countryCode']=cc
            p=get_json('https://geocoding-api.open-meteo.com/v1/search',params,timeout=15)
            rs=p.get('results') or []
            if rs:
                r=rs[0]
                return key,{'latitude':r.get('latitude'),'longitude':r.get('longitude'),'name':r.get('name'),'admin1':r.get('admin1'),'country':r.get('country'),'query':name}
        except Exception:
            pass
    return key,{'error':'unresolved'}

geo={}
with ThreadPoolExecutor(max_workers=16) as ex:
    for f in as_completed([ex.submit(geocode,x) for x in addr_to_sample.items()]):
        k,p=f.result();geo[k]=p
print('geocodes',sum('latitude' in x for x in geo.values()),'of',len(geo),flush=True)

venue_geo={}
for vid,v in venues.items():
    g=geo.get(addr_key(v),{})
    if v.get('indoor') is False and g.get('latitude') is not None:
        venue_geo[vid]=g

# Weather only for actual game dates, batched coordinates. Requests run in parallel.
weather={}; weather_errors=[]
weather_tasks=[]
for date0,day_games in target.groupby('game_date_utc'):
    date1=(pd.Timestamp(date0)+pd.Timedelta(days=1)).date().isoformat()
    for season,sg in day_games.groupby('season'):
        vids=sorted({str(int(v)) for v in pd.to_numeric(sg.venue_id,errors='coerce').dropna().unique() if str(int(v)) in venue_geo})
        for i in range(0,len(vids),12):
            weather_tasks.append((int(season),date0,date1,vids[i:i+12]))

def fetch_weather_task(task):
    season,date0,date1,batch=task
    params={
      'latitude':','.join(str(venue_geo[v]['latitude']) for v in batch),
      'longitude':','.join(str(venue_geo[v]['longitude']) for v in batch),
      'start_date':date0,'end_date':date1,'timezone':'UTC','wind_speed_unit':'mph',
      'hourly':'precipitation,snowfall,weather_code,wind_speed_10m,wind_gusts_10m'}
    try:
        p=get_json('https://historical-forecast-api.open-meteo.com/v1/forecast',params,timeout=30)
        ps=p if isinstance(p,list) else [p]
        if len(ps)!=len(batch): raise ValueError('weather batch length mismatch')
        result=[]
        for vid,item in zip(batch,ps):
            h=item.get('hourly') or {}
            frame=pd.DataFrame({
                'time':pd.to_datetime(h.get('time',[]),utc=True,errors='coerce'),
                'precipitation':pd.to_numeric(pd.Series(h.get('precipitation',[])),errors='coerce'),
                'snowfall':pd.to_numeric(pd.Series(h.get('snowfall',[])),errors='coerce'),
                'weather_code':pd.to_numeric(pd.Series(h.get('weather_code',[])),errors='coerce'),
                'wind_speed_10m':pd.to_numeric(pd.Series(h.get('wind_speed_10m',[])),errors='coerce'),
                'wind_gusts_10m':pd.to_numeric(pd.Series(h.get('wind_gusts_10m',[])),errors='coerce')})
            result.append(((season,vid,date0),frame))
        return result,None
    except Exception as e:
        return [],{'season':season,'date':date0,'venues':batch,'error':repr(e)}

with ThreadPoolExecutor(max_workers=16) as ex:
    futs=[ex.submit(fetch_weather_task,t) for t in weather_tasks]
    done=0
    for f in as_completed(futs):
        result,error=f.result()
        for key,frame in result: weather[key]=frame
        if error: weather_errors.append(error)
        done+=1
        if done % 25 == 0: print('weather batches',done,'of',len(weather_tasks),flush=True)
print('weather retrieval complete',len(weather_tasks),'batches; errors',len(weather_errors),flush=True)

rows=[]
for _,g in target.iterrows():
    season=int(g.season); gid=str(int(g.game_id)); vid='' if pd.isna(g.venue_id) else str(int(float(g.venue_id)))
    vm=venues.get(vid,{})
    try:
        hp=float(g.home_points);ap=float(g.away_points);winner='home' if hp>ap else 'away' if ap>hp else 'tie'
    except Exception:
        winner=None
    row={'season':season,'week':int(g.week),'game_id':int(g.game_id),'away':g.away_team,'home':g.home_team,
         'venue':g.venue,'venue_id':vid,'indoor':vm.get('indoor'),'start_utc':g.start.isoformat(),
         'home_points':g.home_points,'away_points':g.away_points,'winner_side':winner,
         'neutral_site':str(g.get('neutral_site','')).lower() in ['true','t','1','1.0','yes','y']}
    wf=weather.get((season,vid,g.game_date_utc))
    if vm.get('indoor') is False and wf is not None and not wf.empty:
        st=g.start.floor('h'); en=st+pd.Timedelta(hours=4); w=wf[(wf.time>=st)&(wf.time<=en)]
        if not w.empty:
            precip=float(w.precipitation.fillna(0).sum());snow=float(w.snowfall.fillna(0).sum())
            wind=float(w.wind_speed_10m.max()) if w.wind_speed_10m.notna().any() else math.nan
            gust=float(w.wind_gusts_10m.max()) if w.wind_gusts_10m.notna().any() else math.nan
            codes={int(x) for x in w.weather_code.dropna()}
            wet=precip>=1.0 or snow>0 or bool(codes&THUNDER)
            windy=(math.isfinite(wind) and wind>=20) or (math.isfinite(gust) and gust>=30)
            row.update(weather_available=True,precip_mm=precip,snowfall=snow,max_wind_mph=wind,max_gust_mph=gust,
                       wet=wet,windy=windy,inclement=wet or windy,
                       weather_type='Wet/snow + wind' if wet and windy else 'Wet/snow only' if wet else 'Wind only' if windy else 'Ordinary',
                       weather_codes=';'.join(map(str,sorted(codes))))
        else:
            row.update(weather_available=False,inclement=None,weather_type='Missing')
    else:
        row.update(weather_available=False,inclement=None,weather_type='Indoor' if vm.get('indoor') is True else 'Missing')
    rec=profiles.get(gid,{})
    row['profile_status']=rec.get('status','missing')
    if rec.get('status')=='ok':
        h,a=rec['home'],rec['away']
        off='home' if h['off_run']>a['off_run'] else 'away' if a['off_run']>h['off_run'] else None
        de='home' if h['def_run']<a['def_run'] else 'away' if a['def_run']<h['def_run'] else None
        both=off if off and off==de else None
        to_pick='home' if h['margin']>a['margin'] else 'away' if a['margin']>h['margin'] else None
        def_to=de if de and de==to_pick else None
        both_to=both if both and both==to_pick else None
        home_pick=None if row['neutral_site'] else 'home'
        home_def='home' if home_pick and de=='home' else None
        home_to='home' if home_pick and to_pick=='home' else None
        home_both='home' if home_pick and both=='home' else None
        home_def_to='home' if home_pick and def_to=='home' else None
        home_both_to='home' if home_pick and both_to=='home' else None
        row.update(
            home_off_ypc=h['off_run'],away_off_ypc=a['off_run'],
            home_def_ypc_allowed=h['def_run'],away_def_ypc_allowed=a['def_run'],
            home_turnover_margin=h['margin'],away_turnover_margin=a['margin'],
            off_pick=off,def_pick=de,both_pick=both,to_pick=to_pick,def_to_pick=def_to,both_to_pick=both_to,
            home_pick=home_pick,home_def_pick=home_def,home_to_pick=home_to,home_both_pick=home_both,
            home_def_to_pick=home_def_to,home_both_to_pick=home_both_to,
            off_win=(off==winner) if off and winner else None,
            def_win=(de==winner) if de and winner else None,
            both_win=(both==winner) if both and winner else None,
            to_win=(to_pick==winner) if to_pick and winner else None,
            def_to_win=(def_to==winner) if def_to and winner else None,
            both_to_win=(both_to==winner) if both_to and winner else None,
            home_win=(home_pick==winner) if home_pick and winner else None,
            home_def_win=(home_def==winner) if home_def and winner else None,
            home_to_win=(home_to==winner) if home_to and winner else None,
            home_both_win=(home_both==winner) if home_both and winner else None,
            home_def_to_win=(home_def_to==winner) if home_def_to and winner else None,
            home_both_to_win=(home_both_to==winner) if home_both_to and winner else None)
    else:
        row.update(off_pick=None,def_pick=None,both_pick=None,to_pick=None,def_to_pick=None,both_to_pick=None,
                   home_pick=None if row['neutral_site'] else 'home',home_def_pick=None,home_to_pick=None,home_both_pick=None,
                   home_def_to_pick=None,home_both_to_pick=None,
                   off_win=None,def_win=None,both_win=None,to_win=None,def_to_win=None,both_to_win=None,
                   home_win=(winner=='home') if (not row['neutral_site'] and winner) else None,
                   home_def_win=None,home_to_win=None,home_both_win=None,home_def_to_win=None,home_both_to_win=None)
    hg=conference_group(g.home_conference,g.home_team);ag=conference_group(g.away_conference,g.away_team)
    row['group']='P4/P4' if hg=='P4' and ag=='P4' else 'G6/G6' if hg=='G6' and ag=='G6' else 'Mixed/Other'
    rows.append(row)

games=pd.DataFrame(rows)
games.to_csv(OUT/'game_details_hfa_turnover.csv',index=False)
pd.DataFrame(weather_errors).to_csv(OUT/'weather_errors_hfa_turnover.csv',index=False)

def wilson(w,n,z=1.96):
    if not n:return (None,None)
    p=w/n;d=1+z*z/n;c=(p+z*z/(2*n))/d;m=z*math.sqrt((p*(1-p)+z*z/(4*n))/n)/d
    return c-m,c+m
def stat(frame,sig):
    x=frame[frame[sig+'_pick'].notna() & frame[sig+'_win'].notna()]
    n=len(x);w=int(x[sig+'_win'].astype(bool).sum());lo,hi=wilson(w,n)
    return {'games':n,'wins':w,'losses':n-w,'win_rate':w/n if n else None,'wilson_low':lo,'wilson_high':hi}
PRIMARY_SIGNALS=['off','def','both','home','to','def_to','both_to','home_def','home_to','home_both','home_def_to','home_both_to']
def block(frame):
    return {x:stat(frame,x) for x in PRIMARY_SIGNALS}

outdoor=games[(games.indoor==False)&games.weather_available.eq(True)]
inc=outdoor[outdoor.inclement.eq(True)]
ordinary=outdoor[outdoor.inclement.eq(False)]
summary={
 'definition':{'precip_mm_total_gte':1.0,'snowfall_gt':0,'sustained_wind_mph_gte':20.0,'gust_mph_gte':30.0,'thunder_codes':[95,96,99],'window':'kickoff hour through +4h'},
 'coverage':{'target_fbs_games':len(games),'indoor_games':int((games.indoor==True).sum()),'outdoor_weather_available':len(outdoor),
             'outdoor_weather_missing':int(((games.indoor==False)&~games.weather_available.eq(True)).sum()),
             'inclement_games':len(inc),'inclement_with_profiles':int(inc.profile_status.eq('ok').sum()),
             'ordinary_games':len(ordinary),'weather_batch_errors':len(weather_errors),
             'venue_metadata_missing':sum(bool(v.get('_error')) for v in venues.values()),
             'geocodes_missing':sum('latitude' not in v for v in geo.values())},
 'inclement':block(inc),'ordinary_control':block(ordinary),'by_season':{},'by_weather_type':{},'by_group':{}}
for y,f in inc.groupby('season'):summary['by_season'][str(int(y))]=block(f)
for k,f in inc.groupby('weather_type'):summary['by_weather_type'][str(k)]=block(f)
for k,f in inc.groupby('group'):summary['by_group'][str(k)]=block(f)
for sig in PRIMARY_SIGNALS:
    a=summary['inclement'][sig]['win_rate'];b=summary['ordinary_control'][sig]['win_rate']
    summary['inclement'][sig]['vs_ordinary_pp']=None if a is None or b is None else (a-b)*100

(OUT/'summary_hfa_turnover.json').write_text(json.dumps(summary,indent=2))

labels={
 'off':'Higher offensive YPC','def':'Lower defensive YPC allowed','both':'Both YPC advantages',
 'home':'Home field','to':'Better turnover margin/game','def_to':'Run defense + turnover edge',
 'both_to':'Both YPC + turnover edge','home_def':'Home + better run defense',
 'home_to':'Home + turnover edge','home_both':'Home + both YPC advantages',
 'home_def_to':'Home + run defense + turnover edge','home_both_to':'Home + both YPC + turnover edge'}
def fmt(s):
    return '—' if not s['games'] else f"{s['wins']}–{s['losses']} ({s['win_rate']:.1%})"
lines=['# Weather + HFA + turnover validation','',
       'Same locked inclement-weather definition as SPEC.md. Turnover metric is pregame turnover margin per current-season FBS game. Neutral-site games are excluded from home-field signals.','',
       '| Signal | Inclement | Ordinary outdoor | Difference |','|---|---:|---:|---:|']
for sig in PRIMARY_SIGNALS:
    a=summary['inclement'][sig]; b=summary['ordinary_control'][sig]
    d=a.get('vs_ordinary_pp')
    lines.append(f"| {labels[sig]} | {fmt(a)} | {fmt(b)} | {'—' if d is None else f'{d:+.1f} pp'} |")
lines += ['','## P4/P4 inclement weather','','| Signal | Record | Win rate |','|---|---:|---:|']
p4=summary['by_group'].get('P4/P4',{})
for sig in PRIMARY_SIGNALS:
    if sig in p4:
        q=p4[sig]
        lines.append(f"| {labels[sig]} | {q['wins']}–{q['losses']} | {q['win_rate']:.1%} |")
(OUT/'README_HFA_TURNOVER.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(summary,indent=2),flush=True)
