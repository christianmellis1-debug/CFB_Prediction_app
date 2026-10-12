"""Compare 2026 handwritten candidate Test A to published Tier 4 price rule.

Live Tier 4 rule: Week >=4, regular-season FBS, DK moneyline for favorite
from -1000 through -505 inclusive. Result identifies price-rule
eligibility; waterfall may award earlier tier instead. Retrospective prices.
"""
from urllib.request import urlopen,Request
from datetime import datetime,timezone
from pathlib import Path
import json,csv,time,math

D=Path("research/handwritten_offense_defense_2026_10_12")
SRC=D/"favorites_two_test_games.csv"
OUT=D/"tier4_overlap_2026_results.json"
CSV=D/"tier4_overlap_2026_games.csv"
ENDPOINT="https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event="

def ml(v):
    try:
        n=float(str(v).strip().replace("−","-"))
        return int(n) if math.isfinite(n) and n.is_integer() and abs(n)>=100 else None
    except (ValueError,TypeError,OverflowError):
        return None

def summarize(rows):
    wins=sum(r["result"]=="W" for r in rows)
    return {"games":len(rows),"wins":wins,"losses":len(rows)-wins,
            "win_rate":round(wins/len(rows),6) if rows else None}

def get(event):
    error=""
    for i in range(3):
        try:
            req=Request(ENDPOINT+event,headers={"User-Agent":"Mozilla/5.0"})
            with urlopen(req,timeout=24) as f: return json.load(f),""
        except Exception as e:
            error=type(e).__name__+": "+str(e)[:160]
            time.sleep(.22*(i+1))
    return None,error

def inspect(r):
    q={"season":2026,"week":int(r["week"]),"game_id":r["game_id"],
       "home":r["home"],"away":r["away"],"home_group":r["home_group"],
       "spread":float(r["home_team_spread"]),"magnitude":float(r["min_magnitude"]),
       "result":r["result"],"test_A":True,"test_B":r["test_B"]=="True",
       "dk_home_close":None,"dk_away_close":None,
       "dk_home_open":None,"dk_away_open":None,
       "overlap_close":False,"overlap_open":False,"error":""}
    if q["week"]<4: return q
    j,error=get(q["game_id"])
    if error:
        q["error"]=error
        return q
    competition=(((j.get("header") or {}).get("competitions")) or [{}])[0]
    contestants=competition.get("competitors") or []
    home=next((x for x in contestants if x.get("homeAway")=="home"),{})
    away=next((x for x in contestants if x.get("homeAway")=="away"),{})
    hn=(home.get("team") or {}).get("displayName")
    an=(away.get("team") or {}).get("displayName")
    q["espn_home"]=hn
    q["espn_away"]=an
    if str(hn).casefold()!=q["home"].casefold() or str(an).casefold()!=q["away"].casefold():
        q["error"]="ESPN team identity mismatch"
        return q
    bet=j.get("pickcenter") or competition.get("odds") or j.get("odds") or []
    if isinstance(bet,dict): bet=[bet]
    dk=next((o for o in bet if "draft" in str((o.get("provider") or {}).get("name","")).casefold()
              and "king" in str((o.get("provider") or {}).get("name","")).casefold()),None)
    if not dk:
        q["error"]="Missing Draft Kings provider odds"
        return q
    market=dk.get("moneyline") or {}
    def read(side,when):
        return ml((((market.get(side) or {}).get(when) or {}).get("odds")))
    for when in ("close","open"):
        h,a=read("home",when),read("away",when)
        q["dk_home_"+when]=h
        q["dk_away_"+when]=a
        q["overlap_"+when]=(h is not None and a is not None and -1000<=h<=-505 and a>0)
    if q["dk_home_close"] is None or q["dk_away_close"] is None:
        q["error"]="Missing valid Draft Kings closing moneyline"
    return q

def main():
    with SRC.open() as file: all_=list(csv.DictReader(file))
    picks=[x for x in all_ if x["season"]=="2026" and x["test_A"]=="True"]
    assert len(picks)==48 and sum(x["result"]=="W" for x in picks)==40
    results=[inspect(x) for x in picks]
    in_scope=[r for r in results if r["week"]>=4]
    overlap=[r for r in in_scope if r["overlap_close"]]
    opener=[r for r in in_scope if r["overlap_open"]]
    fields=("week","game_id","home","away","home_group","spread","magnitude","result",
            "test_A","test_B","dk_home_close","dk_away_close","dk_home_open",
            "dk_away_open","overlap_close","overlap_open","espn_home","espn_away","error")
    with CSV.open("w",newline="") as file:
        out=csv.DictWriter(file,fields,extrasaction="ignore")
        out.writeheader()
        out.writerows(results)
    record={"retrieved_at":datetime.now(timezone.utc).isoformat(),
            "tier4_rule":"Week 4+ FBS regular-season DK favorite moneyline -1000 to -505 inclusive; home team must be the DK moneyline favorite",
            "odds_source":"ESPN game summary retrospective Draft Kings moneyline; NOT verified historically pregame frozen prices",
            "candidate_test_A":summarize(results),
            "candidate_test_A_week4to6":summarize(in_scope),
            "tier4_price_overlap_closing":summarize(overlap),
            "tier4_price_overlap_opening":summarize(opener),
            "overlap_by_week":{str(w):summarize([r for r in overlap if r["week"]==w]) for w in (3,4,5,6)},
            "overlap_by_group":{g:summarize([r for r in overlap if r["home_group"]==g]) for g in ("P4","G6")},
            "overlap_test_B":[r for r in overlap if r["test_B"]],
            "closing_overlap_games":overlap,
            "opening_overlap_games":opener,
            "missing_odds":[r for r in in_scope if r["error"]],
            "notes":[
             "Week 3 games are impossible Tier 4 matches regardless of their prices.",
             "These are Tier 4 eligibility overlaps, not necessarily displayed Tier 4 waterfall rows, which can be superseded by earlier tiers.",
             "Moneylines may be revised after games. Any missing/invalid odds were not presumed nonqualifying.",
             "No changes to production app."]}
    OUT.write_text(json.dumps(record,indent=2,allow_nan=False)+"\n")
    print(json.dumps(record,indent=2))
if __name__=="__main__": main()
