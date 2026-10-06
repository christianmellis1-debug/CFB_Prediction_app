from urllib.request import urlopen,Request
import json
u='https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/venues/477?lang=en&region=us'
with urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=30) as r:j=json.load(r)
print(sorted(j.keys()))
print(json.dumps(j,indent=2)[:6000])