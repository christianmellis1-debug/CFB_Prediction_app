"""Retrieve archived ESPN game-specific moneylines where ESPN exposes them."""
from urllib.request import urlopen,Request
from urllib.error import URLError,HTTPError
import json
import time
from pathlib import Path
from datetime import datetime,timezone

IDS=[
("3","401856695","Vanderbilt"),("3","401856798","Iowa State"),
("3","401858225","Pittsburgh"),("3","401858231","Duke"),
("3","401858451","Minnesota"),("4","401858241","SMU"),
("4","401858466","Penn State"),("5","401858475","Nebraska"),
("5","401866430","Central Michigan"),("6","401866437","Toledo"),
("6","401866439","Western Michigan"),("6","401870766","Liberty")
]
BASE="https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event="
rows=[]
for w,game,home in IDS:
    record={"week":w,"game_id":game,"selected_home":home}
    try:
        req=Request(BASE+game,headers={"User-Agent":"Mozilla/5.0"})
        with urlopen(req,timeout=18) as response:
            data=json.load(response)
        summary=data.get("header",{})
        comp=(summary.get("competitions") or [{}])[0]
        record["head_comp_keys"]=list(comp)[:35]
        odds=(data.get("pickcenter") or comp.get("odds") or data.get("odds") or [])
        record["odds"]=odds
        record["odds_count"]=len(odds)
        record["odds_kind"]=type(odds).__name__
        competitors=comp.get("competitors",[])
        record["teams"]=[{"team":c.get("team",{}).get("displayName"),"homeAway":c.get("homeAway"),
                          "score":c.get("score")} for c in competitors]
    except Exception as e:
        record["error"]=type(e).__name__+": "+str(e)[:300]
    rows.append(record)
    print(json.dumps(record,default=str)[:2200])
    time.sleep(.18)
path=Path("research/handwritten_offense_defense_2026_10_12/moneyline_audit_2026.json")
path.write_text(json.dumps({"retrieved_at":datetime.now(timezone.utc).isoformat(),
                            "source":"ESPN site API retrospective summary; no verified timestamped pregame capture",
                            "games":rows},indent=2,default=str)+"\n")
