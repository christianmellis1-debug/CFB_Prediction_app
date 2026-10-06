from urllib.request import urlopen
from urllib.parse import urlencode
import json,time
p={'latitude':'40.44,44.98','longitude':'-80.0,-93.26','start_date':'2024-09-14','end_date':'2024-09-15','timezone':'UTC','wind_speed_unit':'mph','hourly':'precipitation,snowfall,weather_code,wind_speed_10m,wind_gusts_10m'}
u='https://historical-forecast-api.open-meteo.com/v1/forecast?'+urlencode(p)
t=time.time()
with urlopen(u,timeout=30) as r:j=json.load(r)
print('seconds',round(time.time()-t,2),'type',type(j).__name__,'len',len(j) if isinstance(j,list) else 1)
print(json.dumps(j if isinstance(j,list) else [j],indent=2)[:3000])