from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor, as_completed
import json, math, time
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'research/weather_ypc_validation/game_details_hfa_turnover.csv'
OUT=ROOT/'research/weather_ypc_validation'
THUNDER={95,96,99}

def get_json(base,params=None,tries=2,timeout=15):
    url=base+('?' + urlencode(params,doseq=True) if params else '')
    last=None
    for i in range(tries):
        try:
            req=Request(url,headers={'User-Agent':'Mozilla/5.0 weather-tier2-parallel'})
            with urlopen(req,timeout=timeout) as r:return json.load(r)
        except Exception as e:
            last=e; time.sleep(.4*(i+1))
    raise last

games=pd.read_csv(DATA,low_memory=False)
for c in ['indoor','neutral_site','weather_available','wet','windy','inclement']:
    if c in games: games[c]=games[c].astype(str).str.lower().map({'true':True,'false':False})
games['start']=pd.to_datetime(games.start_utc,utc=True,errors='coerce')
missing=games[(games.indoor.eq(False)) & (~games.weather_available.eq(True)) & games.start.notna() & games.home_def_to_pick.eq('home')].copy()
print('candidate weather gaps',len(missing),flush=True)

venue_ids=sorted({str(int(float(v))) for v in missing.venue_id.dropna().unique()})
def fetch_venue(vid):
    try:
        p=get_json(f'https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/venues/{vid}',{'lang':'en','region':'us'})
        return vid,p
    except Exception as e:return vid,{'_error':repr(e)}
venues={}
with ThreadPoolExecutor(max_workers=24) as ex:
    for f in as_completed([ex.submit(fetch_venue,v) for v in venue_ids]):
        vid,p=f.result();venues[vid]=p

def addr_key(v):
    a=v.get('address') or {}
    city=str(a.get('city') or '').strip();state=str(a.get('state') or '').strip();country=str(a.get('country') or '').strip()
    return '|'.join([city,state,country]) if city else ''
keys=sorted({addr_key(v) for v in venues.values() if not v.get('_error') and addr_key(v)})

def geo_one(key):
    city,state,country=key.split('|')
    q=', '.join([x for x in [city,state if country in ('USA','United States','US') else country] if x])
    params={'name':q,'count':5,'format':'json','language':'en'}
    if country in ('USA','United States','US'):params['countryCode']='US'
    try:
        p=get_json('https://geocoding-api.open-meteo.com/v1/search',params)
        rs=p.get('results') or []
        if not rs:return key,{'error':'none'}
        chosen=rs[0]
        if state:
            for x in rs:
                if str(x.get('admin1','')).lower()==state.lower():chosen=x;break
        return key,{'latitude':chosen.get('latitude'),'longitude':chosen.get('longitude')}
    except Exception as e:return key,{'error':repr(e)}
geo={}
with ThreadPoolExecutor(max_workers=16) as ex:
    for f in as_completed([ex.submit(geo_one,k) for k in keys]):
        k,v=f.result();geo[k]=v
venue_geo={vid:geo.get(addr_key(v),{}) for vid,v in venues.items()}

tasks=[]
for _,r in missing.iterrows():
    vid=str(int(float(r.venue_id)))
    g=venue_geo.get(vid,{})
    if g.get('latitude') is None:continue
    tasks.append((int(r.season),r.start.date().isoformat(),vid,float(g['latitude']),float(g['longitude'])))
tasks=sorted(set(tasks))
print('weather tasks',len(tasks),flush=True)

def wx_one(t):
    season,date0,vid,lat,lon=t
    date1=(pd.Timestamp(date0)+pd.Timedelta(days=1)).date().isoformat()
    params={'latitude':lat,'longitude':lon,'start_date':date0,'end_date':date1,'timezone':'UTC','wind_speed_unit':'mph',
            'hourly':'precipitation,snowfall,weather_code,wind_speed_10m,wind_gusts_10m'}
    try:
        p=get_json('https://historical-forecast-api.open-meteo.com/v1/forecast',params,tries=2,timeout=20)
        h=p.get('hourly') or {}
        frame=pd.DataFrame({'time':pd.to_datetime(h.get('time',[]),utc=True,errors='coerce'),
                            'precipitation':pd.to_numeric(pd.Series(h.get('precipitation',[])),errors='coerce'),
                            'snowfall':pd.to_numeric(pd.Series(h.get('snowfall',[])),errors='coerce'),
                            'weather_code':pd.to_numeric(pd.Series(h.get('weather_code',[])),errors='coerce'),
                            'wind_speed_10m':pd.to_numeric(pd.Series(h.get('wind_speed_10m',[])),errors='coerce'),
                            'wind_gusts_10m':pd.to_numeric(pd.Series(h.get('wind_gusts_10m',[])),errors='coerce')})
        return (season,date0,vid),frame,None
    except Exception as e:return (season,date0,vid),None,repr(e)

weather={};errors=[]
with ThreadPoolExecutor(max_workers=20) as ex:
    for f in as_completed([ex.submit(wx_one,t) for t in tasks]):
        k,frame,err=f.result()
        if err:errors.append({'season':k[0],'date':k[1],'venue_id':k[2],'error':err})
        else:weather[k]=frame
print('weather recovered',len(weather),'errors',len(errors),flush=True)

mask=(games.indoor.eq(False)) & (~games.weather_available.eq(True)) & games.start.notna() & games.home_def_to_pick.eq('home')
for idx,row in games[mask].iterrows():
    season=int(row.season); date0=row.start.date().isoformat(); vid=str(int(float(row.venue_id)))
    wf=weather.get((season,date0,vid))
    if wf is None or wf.empty:continue
    st=row.start.floor('h'); en=st+pd.Timedelta(hours=4); w=wf[(wf.time>=st)&(wf.time<=en)]
    if w.empty:continue
    precip=float(w.precipitation.fillna(0).sum()); snow=float(w.snowfall.fillna(0).sum())
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

games.to_csv(DATA,index=False)
pd.DataFrame(errors).to_csv(OUT/'weather_errors_tier2_parallel.csv',index=False)
cand=games[games.inclement.eq(True) & games.home_def_to_pick.eq('home')].copy()
print('candidate count',len(cand),'record',int(cand.home_def_to_win.astype(str).str.lower().eq('true').sum()),'-',int(cand.home_def_to_win.astype(str).str.lower().eq('false').sum()),flush=True)
cand[['season','week','game_id','away','home','group','weather_type','precip_mm','max_wind_mph','max_gust_mph','home_def_ypc_allowed','away_def_ypc_allowed','home_turnover_margin','away_turnover_margin','home_def_to_win']].to_csv(ROOT/'research/weather_tier2_market_validation/recovered_candidates.csv',index=False)