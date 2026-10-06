from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor, as_completed
import json, math, time, sys
import pandas as pd
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from matchup_advantages import build_waterfall_profiles, conference_group, normalize_fbs_schedule

OUT=Path(__file__).resolve().parent
SEASONS=[2024,2025,2026]
THUNDER={95,96,99}

def get_json(base,params=None,tries=3):
    url=base+('?' + urlencode(params,doseq=True) if params else '')
    last=None
    for attempt in range(tries):
        try:
            req=Request(url,headers={'User-Agent':'Mozilla/5.0 weather-ypc-research'})
            with urlopen(req,timeout=60) as r:return json.load(r)
        except Exception as e:
            last=e; time.sleep(1.5*(attempt+1))
    raise last

def truthy(series):
    return series.astype(str).str.lower().isin(['true','t','1','1.0','yes','y'])

# Load schedules and target completed regular-season FBS-vs-FBS games.
schedules={}; targets=[]
for season in SEASONS:
    u=f'https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{season}.csv'
    s=pd.read_csv(u,low_memory=False)
    schedules[season]=s
    n=normalize_fbs_schedule(s)
    mask=n.season_type.astype(str).str.lower().eq('regular') & truthy(n.completed)
    if season==2026: mask &= pd.to_numeric(n.week,errors='coerce').le(5)
    t=n[mask].copy()
    t['season']=season
    targets.append(t)
target=pd.concat(targets,ignore_index=True)
target['game_id']=pd.to_numeric(target.game_id,errors='coerce').astype('Int64')
target['start']=pd.to_datetime(target.start_date,utc=True,errors='coerce')
target=target.dropna(subset=['game_id','start'])

# ESPN core venue metadata gives indoor flag and address.
venue_ids=sorted({str(int(v)) for v in pd.to_numeric(target.venue_id,errors='coerce').dropna().unique()})
def fetch_venue(vid):
    base=f'https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/venues/{vid}'
    try:return vid,get_json(base,{'lang':'en','region':'us'})
    except Exception as e:return vid,{'_error':repr(e)}

venues={}
with ThreadPoolExecutor(max_workers=12) as ex:
    futs=[ex.submit(fetch_venue,v) for v in venue_ids]
    for f in as_completed(futs):
        vid,p=f.result(); venues[vid]=p
(OUT/'venue_metadata.json').write_text(json.dumps(venues,indent=2))

# Geocode each outdoor venue from ESPN's address. Cache by address key.
def addr_key(v):
    a=v.get('address') or {}
    city=str(a.get('city') or '').strip(); state=str(a.get('state') or '').strip(); country=str(a.get('country') or '').strip()
    return '|'.join([city,state,country]) if city else ''

address_keys=sorted({addr_key(v) for v in venues.values() if not v.get('_error') and v.get('indoor') is False and addr_key(v)})
def geocode(key):
    city,state,country=key.split('|')
    name=', '.join([x for x in [city,state if country in ('USA','United States','US') else country] if x])
    params={'name':name,'count':5,'format':'json','language':'en'}
    if country in ('USA','United States','US'):params['countryCode']='US'
    try:
        p=get_json('https://geocoding-api.open-meteo.com/v1/search',params)
        results=p.get('results') or []
        if not results:return key,{'error':'no results','query':name}
        # Prefer requested state/admin area when possible, otherwise first result.
        chosen=results[0]
        if state:
            for r in results:
                if str(r.get('admin1','')).lower()==state.lower() or str(r.get('admin1','')).lower().startswith(state.lower()):
                    chosen=r;break
        return key,{'query':name,'latitude':chosen.get('latitude'),'longitude':chosen.get('longitude'),'name':chosen.get('name'),'admin1':chosen.get('admin1'),'country':chosen.get('country'),'timezone':chosen.get('timezone')}
    except Exception as e:return key,{'error':repr(e),'query':name}

geo={}
with ThreadPoolExecutor(max_workers=8) as ex:
    futs=[ex.submit(geocode,k) for k in address_keys]
    for f in as_completed(futs):
        k,p=f.result();geo[k]=p
(OUT/'geocodes.json').write_text(json.dumps(geo,indent=2))

# Map venue id to resolved coordinate.
venue_geo={}
for vid,v in venues.items():
    k=addr_key(v); g=geo.get(k,{})
    if v.get('indoor') is False and g.get('latitude') is not None and g.get('longitude') is not None:
        venue_geo[vid]=g

# Fetch hourly historical forecasts in coordinate batches for each season.
weather={}; weather_errors=[]
for season in SEASONS:
    season_games=target[target.season.eq(season)]
    vids=[]
    for v in pd.to_numeric(season_games.venue_id,errors='coerce').dropna().unique():
        vid=str(int(v))
        if vid in venue_geo:vids.append(vid)
    vids=sorted(set(vids))
    if not vids:continue
    start=season_games.start.min().date().isoformat()
    end=(season_games.start.max()+pd.Timedelta(days=1)).date().isoformat()
    for i in range(0,len(vids),8):
        batch=vids[i:i+8]
        params={
          'latitude':','.join(str(venue_geo[v]['latitude']) for v in batch),
          'longitude':','.join(str(venue_geo[v]['longitude']) for v in batch),
          'start_date':start,'end_date':end,'timezone':'UTC','wind_speed_unit':'mph',
          'hourly':'precipitation,snowfall,weather_code,wind_speed_10m,wind_gusts_10m'}
        try:
            p=get_json('https://historical-forecast-api.open-meteo.com/v1/forecast',params)
            payloads=p if isinstance(p,list) else [p]
            if len(payloads)!=len(batch):raise ValueError(f'weather batch length {len(payloads)} != {len(batch)}')
            for vid,item in zip(batch,payloads):
                h=item.get('hourly') or {}
                times=pd.to_datetime(h.get('time',[]),utc=True,errors='coerce')
                frame=pd.DataFrame({
                    'time':times,
                    'precipitation':pd.to_numeric(pd.Series(h.get('precipitation',[])),errors='coerce'),
                    'snowfall':pd.to_numeric(pd.Series(h.get('snowfall',[])),errors='coerce'),
                    'weather_code':pd.to_numeric(pd.Series(h.get('weather_code',[])),errors='coerce'),
                    'wind_speed_10m':pd.to_numeric(pd.Series(h.get('wind_speed_10m',[])),errors='coerce'),
                    'wind_gusts_10m':pd.to_numeric(pd.Series(h.get('wind_gusts_10m',[])),errors='coerce')})
                weather[(season,vid)]=frame.dropna(subset=['time'])
        except Exception as e:
            weather_errors.append({'season':season,'venues':batch,'error':repr(e)})

# Build pregame raw rushing profiles by target week.
profiles={}
for season in SEASONS:
    box_url=f'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_{season}.csv'
    boxes=pd.read_csv(box_url,low_memory=False)
    s=schedules[season]
    weeks=sorted(pd.to_numeric(target.loc[target.season.eq(season),'week'],errors='coerce').dropna().astype(int).unique())
    for week in weeks:
        checks=build_waterfall_profiles(s,boxes,week)
        profiles.update({str(k):v for k,v in checks.items()})

rows=[]
for _,g in target.iterrows():
    gid=str(int(g.game_id)); season=int(g.season)
    vid='' if pd.isna(g.venue_id) else str(int(float(g.venue_id)))
    vm=venues.get(vid,{})
    indoor=vm.get('indoor')
    row={'season':season,'week':int(g.week),'game_id':int(g.game_id),'away':g.away_team,'home':g.home_team,
         'venue':g.venue,'venue_id':vid,'indoor':indoor,'start_utc':g.start.isoformat(),
         'home_points':g.home_points,'away_points':g.away_points}
    try:
        hp=float(g.home_points);ap=float(g.away_points)
        winner='home' if hp>ap else 'away' if ap>hp else 'tie'
    except: winner=None
    row['winner_side']=winner
    # Weather window is kickoff hour through four hours after kickoff.
    wf=weather.get((season,vid))
    if indoor is False and wf is not None and not wf.empty:
        start=g.start.floor('h'); end=start+pd.Timedelta(hours=4)
        w=wf[(wf.time>=start)&(wf.time<=end)]
        if not w.empty:
            precip=float(w.precipitation.fillna(0).sum()); snow=float(w.snowfall.fillna(0).sum())
            wind=float(w.wind_speed_10m.max()) if w.wind_speed_10m.notna().any() else math.nan
            gust=float(w.wind_gusts_10m.max()) if w.wind_gusts_10m.notna().any() else math.nan
            codes={int(x) for x in w.weather_code.dropna().tolist()}
            wet=(precip>=1.0) or (snow>0) or bool(codes & THUNDER)
            windy=(math.isfinite(wind) and wind>=20.0) or (math.isfinite(gust) and gust>=30.0)
            inclement=wet or windy
            wtype='Wet/snow + wind' if wet and windy else 'Wet/snow only' if wet else 'Wind only' if windy else 'Ordinary'
            row.update(weather_available=True,precip_mm=precip,snowfall=float(snow),max_wind_mph=wind,max_gust_mph=gust,
                       weather_codes=';'.join(map(str,sorted(codes))),wet=wet,windy=windy,inclement=inclement,weather_type=wtype)
        else:row.update(weather_available=False,inclement=None,weather_type='Missing')
    else:row.update(weather_available=False,inclement=None,weather_type='Indoor' if indoor is True else 'Missing')
    rec=profiles.get(gid,{})
    row['profile_status']=rec.get('status','missing')
    if rec.get('status')=='ok':
        h,a=rec['home'],rec['away']
        row.update(home_off_ypc=h['off_run'],away_off_ypc=a['off_run'],home_def_ypc_allowed=h['def_run'],away_def_ypc_allowed=a['def_run'])
        off_pick='home' if h['off_run']>a['off_run'] else 'away' if a['off_run']>h['off_run'] else None
        def_pick='home' if h['def_run']<a['def_run'] else 'away' if a['def_run']<h['def_run'] else None
        both_pick=off_pick if off_pick is not None and off_pick==def_pick else None
        row.update(off_pick=off_pick,def_pick=def_pick,both_pick=both_pick,
                   off_win=(off_pick==winner) if off_pick and winner else None,
                   def_win=(def_pick==winner) if def_pick and winner else None,
                   both_win=(both_pick==winner) if both_pick and winner else None)
    else:row.update(off_pick=None,def_pick=None,both_pick=None,off_win=None,def_win=None,both_win=None)
    hg=conference_group(g.home_conference,g.home_team);ag=conference_group(g.away_conference,g.away_team)
    row['group']='P4/P4' if hg=='P4' and ag=='P4' else 'G6/G6' if hg=='G6' and ag=='G6' else 'Mixed/Other'
    rows.append(row)

games=pd.DataFrame(rows)
games.to_csv(OUT/'game_details.csv',index=False)
pd.DataFrame(weather_errors).to_csv(OUT/'weather_errors.csv',index=False)

def wilson(w,n,z=1.96):
    if not n:return (None,None)
    p=w/n;d=1+z*z/n;c=(p+z*z/(2*n))/d;m=z*math.sqrt((p*(1-p)+z*z/(4*n))/n)/d
    return (c-m,c+m)

def signal_stats(frame,col):
    pick=col+'_pick';win=col+'_win'
    x=frame[frame[pick].notna() & frame[win].notna()]
    n=len(x);w=int(x[win].astype(bool).sum());lo,hi=wilson(w,n)
    return {'games':n,'wins':w,'losses':n-w,'win_rate':w/n if n else None,'wilson_low':lo,'wilson_high':hi}

def block(frame):
    return {k:signal_stats(frame,k) for k in ['off','def','both']}

outdoor=games[(games.indoor==False)&games.weather_available.eq(True)]
inc=outdoor[outdoor.inclement.eq(True)]
ordinary=outdoor[outdoor.inclement.eq(False)]
summary={
 'definition':{'precip_mm_total_gte':1.0,'snowfall_gt':0,'sustained_wind_mph_gte':20.0,'gust_mph_gte':30.0,'thunder_codes':[95,96,99],'window':'kickoff hour through +4h'},
 'coverage':{'target_fbs_games':len(games),'indoor_games':int((games.indoor==True).sum()),'outdoor_weather_available':len(outdoor),
             'outdoor_weather_missing':int(((games.indoor==False)&~games.weather_available.eq(True)).sum()),
             'inclement_games':len(inc),'inclement_with_profiles':int(inc.profile_status.eq('ok').sum()),
             'ordinary_games':len(ordinary),'weather_batch_errors':len(weather_errors)},
 'inclement':block(inc),'ordinary_control':block(ordinary),'by_season':{},'by_weather_type':{},'by_group':{}}

for season,f in inc.groupby('season'):summary['by_season'][str(int(season))]=block(f)
for wt,f in inc.groupby('weather_type'):summary['by_weather_type'][str(wt)]=block(f)
for grp,f in inc.groupby('group'):summary['by_group'][str(grp)]=block(f)

for sig in ['off','def','both']:
    a=summary['inclement'][sig]['win_rate'];b=summary['ordinary_control'][sig]['win_rate']
    summary['inclement'][sig]['vs_ordinary_pp']=None if a is None or b is None else (a-b)*100

(OUT/'summary.json').write_text(json.dumps(summary,indent=2))

# Compact markdown report.
def fmt(s):
    if not s['games']:return '—'
    return f"{s['wins']}–{s['losses']} ({s['win_rate']:.1%})"
lines=['# Weather × YPC validation results','',
       f"Target games: {summary['coverage']['target_fbs_games']}; outdoor games with weather: {summary['coverage']['outdoor_weather_available']}; inclement games: {summary['coverage']['inclement_games']}; inclement games with usable pregame rushing profiles: {summary['coverage']['inclement_with_profiles']}.",'',
       '| Signal | Inclement | Ordinary outdoor | Difference |','|---|---:|---:|---:|']
labels={'off':'Higher offensive YPC','def':'Lower defensive YPC allowed','both':'Both advantages'}
for sig in ['off','def','both']:
    a=summary['inclement'][sig];b=summary['ordinary_control'][sig];d=a.get('vs_ordinary_pp')
    lines.append(f"| {labels[sig]} | {fmt(a)} | {fmt(b)} | {'—' if d is None else f'{d:+.1f} pp'} |")
lines += ['','## Inclement by season','','| Season | Higher offensive YPC | Lower defensive YPC allowed | Both |','|---|---:|---:|---:|']
for season,d in summary['by_season'].items():lines.append(f"| {season} | {fmt(d['off'])} | {fmt(d['def'])} | {fmt(d['both'])} |")
lines += ['','## Inclement by weather type','','| Type | Higher offensive YPC | Lower defensive YPC allowed | Both |','|---|---:|---:|---:|']
for wt,d in summary['by_weather_type'].items():lines.append(f"| {wt} | {fmt(d['off'])} | {fmt(d['def'])} | {fmt(d['both'])} |")
lines += ['','## Inclement by matchup group','','| Group | Higher offensive YPC | Lower defensive YPC allowed | Both |','|---|---:|---:|---:|']
for grp,d in summary['by_group'].items():lines.append(f"| {grp} | {fmt(d['off'])} | {fmt(d['def'])} | {fmt(d['both'])} |")
lines += ['','See SPEC.md for the locked definition and game_details.csv for every game and weather reading. No production changes.']
(OUT/'README.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(summary,indent=2))