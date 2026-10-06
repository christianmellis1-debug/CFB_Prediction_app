from urllib.request import urlopen, Request
import json
from pathlib import Path
ids=['401635547','401628487','401628414','401858202']
out={}
for gid in ids:
    u='https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event='+gid
    req=Request(u,headers={'User-Agent':'Mozilla/5.0'})
    with urlopen(req,timeout=25) as r:p=json.load(r)
    out[gid]={
      'top_keys':sorted(p.keys()),
      'gameInfo':p.get('gameInfo'),
      'header_competition':(p.get('header',{}).get('competitions') or [{}])[0],
      'weather':p.get('weather'),
    }
Path('research/weather_ypc_validation/sample_summary.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2)[:20000])