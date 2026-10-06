from urllib.request import urlopen
import json
from pathlib import Path
event="401858258"
u="https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event="+event
with urlopen(u,timeout=20) as r:
    p=json.load(r)
out={"event":event,"pickcenter":p.get("pickcenter",[]),"competition_odds":[c.get("odds",[]) for c in p.get("header",{}).get("competitions",[])]}
Path("research/spread_payload_sample.json").write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2)[:12000])
