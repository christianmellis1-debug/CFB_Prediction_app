from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor, as_completed
import json, math, time
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
THUNDER={95,96,99}

def get_json(base,params=None,tries=5,timeout=30):
    url=base+('?' + urlencode(params,doseq=True) if params else '')
    last=None
    for attempt in range(tries):
        try:
            req=Request(url,headers={'User-Agent':'Mozilla/5.0 weather-ypc-retry'})
            with urlopen(req,timeout=timeout) as r:return json.load(r)
        except Exception as e:
            last=e; time.sleep(1.5*(attempt+1))
    raise last

games=pd.read_csv(OUT/'game_details_hfa_turnover.csv',low_memory=False)
for c in ['indoor','neutral_site','weather_available','wet','windy','inclement']:
    if c in games:
        games[c]=games[c].astype(str).str.lower().map({'true':True,'false':False})
games['start']=pd.to_datetime(games.start_utc,utc=True,errors='coerce')
missing=games[(games.indoor.eq(False)) & (~games.weather_available.eq(True)) & games.start.notna() & games.home_def_to_pick.eq('home')].copy()
print('missing home+defense+turnover candidate rows',len(missing),flush=True)

# Venue metadata for only unresolved games.
venue_ids=sorted({str(int(float(v))) for v in missing.venue_id.dropna().unique()})
def fetch_venue(vid):
    try:
        return vid,get_json(f'https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/venues/{vid}',{'lang':'en','region':'us'},timeout=15)
    except Exception as e:return vid,{'_error':repr(e)}
venues={}
with ThreadPoolExecutor(max_workers=8) as ex:
    for f in as_completed([ex.submit(fetch_venue,v) for v in venue_ids]):
        vid,p=f.result();venues[vid]=p

def addr_key(v):
    a=v.get('address') or {}
    city=str(a.get('city') or '').strip();state=str(a.get('state') or '').strip();country=str(a.get('country') or '').strip()
    return '|'.join([city,state,country]) if city else ''

keys=sorted({addr_key(v) for v in venues.values() if not v.get('_error') and addr_key(v)})
geo={}
for i,key in enumerate(keys):
    city,state,country=key.split('|')
    q=', '.join([x for x in [city,state if country in ('USA','United States','US') else country] if x])
    params={'name':q,'count':5,'format':'json','language':'en'}
    if country in ('USA','United States','US'):params['countryCode']='US'
    try:
        p=get_json('https://geocoding-api.open-meteo.com/v1/search',params,tries=3,timeout=20)
        rs=p.get('results') or []
        if rs:
            chosen=rs[0]
            if state:
                for x in rs:
                    if str(x.get('admin1','')).lower()==state.lower():chosen=x;break
            geo[key]={'latitude':chosen.get('latitude'),'longitude':chosen.get('longitude')}
    except Exception:pass
    time.sleep(.12)

venue_geo={vid:geo.get(addr_key(v),{}) for vid,v in venues.items()}
updates={}; errors=[]
missing['date']=missing.start.dt.date.astype(str)
tasks=[]
for (season,date0),g in missing.groupby(['season','date']):
    vids=sorted({str(int(float(v))) for v in g.venue_id.dropna().unique() if venue_geo.get(str(int(float(v))),{}).get('latitude') is not None})
    for i in range(0,len(vids),8):tasks.append((int(season),date0,vids[i:i+8]))
print('retry weather batches',len(tasks),flush=True)

for n,(season,date0,batch) in enumerate(tasks,1):
    date1=(pd.Timestamp(date0)+pd.Timedelta(days=1)).date().isoformat()
    params={'latitude':','.join(str(venue_geo[v]['latitude']) for v in batch),
            'longitude':','.join(str(venue_geo[v]['longitude']) for v in batch),
            'start_date':date0,'end_date':date1,'timezone':'UTC','wind_speed_unit':'mph',
            'hourly':'precipitation,snowfall,weather_code,wind_speed_10m,wind_gusts_10m'}
    try:
        p=get_json('https://historical-forecast-api.open-meteo.com/v1/forecast',params,tries=5,timeout=40)
        ps=p if isinstance(p,list) else [p]
        if len(ps)!=len(batch):raise ValueError('batch length mismatch')
        for vid,item in zip(batch,ps):
            h=item.get('hourly') or {}
            frame=pd.DataFrame({'time':pd.to_datetime(h.get('time',[]),utc=True,errors='coerce'),
                                'precipitation':pd.to_numeric(pd.Series(h.get('precipitation',[])),errors='coerce'),
                                'snowfall':pd.to_numeric(pd.Series(h.get('snowfall',[])),errors='coerce'),
                                'weather_code':pd.to_numeric(pd.Series(h.get('weather_code',[])),errors='coerce'),
                                'wind_speed_10m':pd.to_numeric(pd.Series(h.get('wind_speed_10m',[])),errors='coerce'),
                                'wind_gusts_10m':pd.to_numeric(pd.Series(h.get('wind_gusts_10m',[])),errors='coerce')})
            updates[(season,date0,vid)]=frame
    except Exception as e:errors.append({'season':season,'date':date0,'venues':batch,'error':repr(e)})
    if n%10==0:print('retried',n,'of',len(tasks),'errors',len(errors),flush=True)
    time.sleep(.45)

# Fill only previously missing weather rows.
for idx,row in games[(games.indoor.eq(False)) & (~games.weather_available.eq(True)) & games.start.notna() & games.home_def_to_pick.eq('home')].iterrows():
    season=int(row.season);date0=row.start.date().isoformat();vid=str(int(float(row.venue_id)))
    wf=updates.get((season,date0,vid))
    if wf is None or wf.empty:continue
    st=row.start.floor('h');en=st+pd.Timedelta(hours=4);w=wf[(wf.time>=st)&(wf.time<=en)]
    if w.empty:continue
    precip=float(w.precipitation.fillna(0).sum());snow=float(w.snowfall.fillna(0).sum())
    wind=float(w.wind_speed_10m.max()) if w.wind_speed_10m.notna().any() else math.nan
    gust=float(w.wind_gusts_10m.max()) if w.wind_gusts_10m.notna().any() else math.nan
    codes={int(x) for x in w.weather_code.dropna()}
    wet=precip>=1.0 or snow>0 or bool(codes&THUNDER)
    windy=(math.isfinite(wind) and wind>=20) or (math.isfinite(gust) and gust>=30)
    vals={'weather_available':True,'precip_mm':precip,'snowfall':snow,'max_wind_mph':wind,'max_gust_mph':gust,
          'wet':wet,'windy':windy,'inclement':wet or windy,
          'weather_type':'Wet/snow + wind' if wet and windy else 'Wet/snow only' if wet else 'Wind only' if windy else 'Ordinary',
          'weather_codes':';'.join(map(str,sorted(codes)))}
    for k,v in vals.items():games.at[idx,k]=v

def wilson(w,n,z=1.96):
    if not n:return (None,None)
    p=w/n;d=1+z*z/n;c=(p+z*z/(2*n))/d;m=z*math.sqrt((p*(1-p)+z*z/(4*n))/n)/d
    return c-m,c+m
PRIMARY=['off','def','both','home','to','def_to','both_to','home_def','home_to','home_both','home_def_to','home_both_to']
def stat(frame,sig):
    pick=sig+'_pick';win=sig+'_win'
    x=frame[frame[pick].notna() & frame[win].notna()]
    vals=x[win].astype(str).str.lower().map({'true':True,'false':False}).dropna()
    n=len(vals);w=int(vals.sum());lo,hi=wilson(w,n)
    return {'games':n,'wins':w,'losses':n-w,'win_rate':w/n if n else None,'wilson_low':lo,'wilson_high':hi}
def block(f):return {s:stat(f,s) for s in PRIMARY}

games.to_csv(OUT/'game_details_hfa_turnover.csv',index=False)
pd.DataFrame(errors).to_csv(OUT/'weather_errors_hfa_turnover_retry.csv',index=False)
outdoor=games[(games.indoor.eq(False)) & games.weather_available.eq(True)]
inc=outdoor[games.loc[outdoor.index,'inclement'].eq(True)]
ordinary=outdoor[games.loc[outdoor.index,'inclement'].eq(False)]
summary={'definition':{'precip_mm_total_gte':1.0,'snowfall_gt':0,'sustained_wind_mph_gte':20.0,'gust_mph_gte':30.0,'thunder_codes':[95,96,99],'window':'kickoff hour through +4h'},
         'coverage':{'target_fbs_games':len(games),'indoor_games':int(games.indoor.eq(True).sum()),'outdoor_weather_available':len(outdoor),
                     'outdoor_weather_missing':int(((games.indoor.eq(False)) & (~games.weather_available.eq(True))).sum()),
                     'inclement_games':len(inc),'inclement_with_profiles':int(inc.profile_status.eq('ok').sum()),'ordinary_games':len(ordinary),'retry_errors':len(errors)},
         'inclement':block(inc),'ordinary_control':block(ordinary),'by_season':{},'by_weather_type':{},'by_group':{}}
for y,g in inc.groupby('season'):summary['by_season'][str(int(y))]=block(g)
for k,g in inc.groupby('weather_type'):summary['by_weather_type'][str(k)]=block(g)
for k,g in inc.groupby('group'):summary['by_group'][str(k)]=block(g)
for sig in PRIMARY:
    a=summary['inclement'][sig]['win_rate'];b=summary['ordinary_control'][sig]['win_rate']
    summary['inclement'][sig]['vs_ordinary_pp']=None if a is None or b is None else (a-b)*100
(OUT/'summary_hfa_turnover.json').write_text(json.dumps(summary,indent=2))
candidate_count=int((games.inclement.eq(True) & games.home_def_to_pick.eq('home')).sum())
print('recovered candidate count',candidate_count,flush=True)
print(json.dumps(summary,indent=2),flush=True)