from urllib.request import urlopen, Request
import json
from pathlib import Path
venues=['477','3714','3953','3752']
out={}
for vid in venues:
    u='https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/venues/'+vid+'?lang=en&region=us'
    req=Request(u,headers={'User-Agent':'Mozilla/5.0'})
    with urlopen(req,timeout=25) as r:p=json.load(r)
    out[vid]=p
Path('research/weather_ypc_validation/venue_sample.json').write_text(json.dumps(out,indent=2))
print(json.dumps({k:{x:v.get(x) for x in ['id','fullName','indoor','grass','address']} for k,v in out.items()},indent=2))