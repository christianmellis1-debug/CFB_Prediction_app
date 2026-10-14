"""Audit historical moneylines for 2025 teams with >=7 pregame net ATS disparity.

Research-only: use ESPN core-v2 historic odds, identify the provider and snapshot.
No synthetic line conversions from point spread.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen
import json
import math

from ats_discrepancy_2024_2025 import season_data, run

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; research; historical-data)",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.espn.com",
    "Referer": "https://www.espn.com/",
}
def get_payload(gid):
    url = ("https://sports.core.api.espn.com/v2/sports/football/leagues/"
           f"college-football/events/{gid}/competitions/{gid}/odds?lang=en&region=us&limit=100")
    try:
        with urlopen(Request(url,headers=HEADERS),timeout=20) as response:
            return gid,json.load(response),None
    except Exception as e:
        return gid,{},str(e)[:170]

def valid_price(x):
    try:
        if x is None or isinstance(x,bool):
            return None
        x=str(x).strip().replace("−","-")
        if x.upper() in ("EVEN","EV","EVS"): return 100
        x=float(x)
        if not math.isfinite(x) or abs(x)<100 or not x.is_integer(): return None
        return int(x)
    except (ValueError,TypeError):
        return None

def extract_price(team_odds):
    if not isinstance(team_odds,dict):
        return None, "missing"
    close=team_odds.get("close",{})
    if isinstance(close,dict):
        m=close.get("moneyLine",{})
        if isinstance(m,dict):
            for k in ("american","value","displayValue"):
                v=valid_price(m.get(k))
                if v is not None:return v, "close"
        else:
            if valid_price(m) is not None:return valid_price(m),"close"
    top=valid_price(team_odds.get("moneyLine"))
    if top is not None:
        return top,"top-level (snapshot not confirmed)"
    curr=team_odds.get("current",{})
    if isinstance(curr,dict):
        m=curr.get("moneyLine",{})
        if isinstance(m,dict):
            for k in ("american","value"):
                v=valid_price(m.get(k))
                if v is not None:return v, "current (not verified close)"
    return None,"missing"

def american_profit(ml, stake=100):
    return stake*(100/abs(ml) if ml<0 else ml/100)

def implied_prob(ml):
    return abs(ml)/(abs(ml)+100) if ml<0 else 100/(ml+100)

def main():
    rows=run(2025,season_data(2025))
    games=[r for r in rows if r["net_gap"]>=7 and r["stronger_line"]<0]
    print("QUALIFYING_FAVORITES",len(games),"SU_WINS",sum(x["better_ats_won_su"] for x in games))
    fetch_results={}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs=[pool.submit(get_payload,g["game_id"]) for g in games]
        for fut in as_completed(futs):
            gid,payload,error=fut.result()
            fetch_results[gid]=(payload,error)
    choices=[]
    for r in games:
        gid=r["game_id"]
        payload,error=fetch_results[gid]
        items=payload.get("items",[]) if isinstance(payload,dict) else []
        if gid in [401752875,401752882,401756933]:
            print("PAYLOAD_EXAMPLE",gid,"keys",list(payload) if payload else [],"error",error,"count",len(items))
            for it in items[:3]:
                print("EXAMPLE_ITEM",gid, json.dumps({
                    "provider":it.get("provider"),
                    "homeTeamOdds":it.get("homeTeamOdds"),
                    "awayTeamOdds":it.get("awayTeamOdds"),
                    "status":it.get("status")
                },ensure_ascii=False)[:2000])
        candidates=[]
        for item in items:
            prov=item.get("provider") or {}
            if not isinstance(prov,dict): prov={}
            team=(item.get("homeTeamOdds") if r["stronger_is_home"] else item.get("awayTeamOdds"))
            price,snap=extract_price(team)
            if price is None:continue
            name=str(prov.get("name") or "Unknown")
            p=prov.get("priority",999)
            try:p=int(p)
            except (ValueError,TypeError):p=999
            candidates.append((name,p,price,snap))
        # Comparable primary book, falling back to another provider only
        # when DraftKings is unavailable, and preferring closing snapshots.
        candidates.sort(key=lambda c:(0 if c[0].lower().replace(" ","")=="draftkings" else 1,
                                      0 if c[3]=="close" else 1,
                                      c[1],c[0]))
        choice=candidates[0] if candidates else None
        if choice:
            provider,_,ml,snap=choice
            ev=american_profit(ml) if r["better_ats_won_su"] else -100
            ip=implied_prob(ml)
        else:
            provider,ml,snap,ev,ip="N/A",None,"missing",None,None
        v={**r,"moneyline":ml,"provider":provider,"snapshot":snap,"net":ev,"implied":ip}
        choices.append(v)
        print("ML_DETAIL|"+ "|".join(map(str,[
            r["week"],r["net_gap"],r["favored_by_ats"],r["matchup"],r["stronger_line"],r["better_ats_won_su"],
            provider, f"{ml:+d}" if ml is not None else "N/A",
            snap,f"{ev:+.2f}" if ev is not None else "N/A", gid,
            "ERROR:"+error if error else "", "PROVIDERS:"+str(len(candidates))
        ])))
    print("COVERAGE",len(choices),sum(v["moneyline"] is not None for v in choices),
          "close",sum(v["snapshot"]=="close" for v in choices),
          "errors",sum(fetch_results[g["game_id"]][1] is not None for g in games))
    for label,pool in [
        ("all", choices),("close_only",[v for v in choices if v["snapshot"]=="close"]),
        ("DK",[v for v in choices if v["provider"].lower().replace(" ","")=="draftkings"]),
    ]:
        found=[r for r in pool if r["moneyline"] is not None]
        wins=sum(r["better_ats_won_su"] for r in found)
        total_profit=sum(r["net"] for r in found)
        expected_wins=sum(r["implied"] for r in found)
        print("SUMMARY",label,"games",len(found),"w-l",wins,len(found)-wins,
              "total_net_100",round(total_profit,2),
              "ROI",round(100*total_profit/(100*len(found)),2) if found else "N/A",
              "mean_book_implied",round(100*expected_wins/len(found),2) if found else "N/A",
              "expected_wins_book_implied",round(expected_wins,2),
              "missing",len(pool)-len(found))
    print("BUCKETS")
    for label,fn in [("-100_to_-199",lambda ml:-200<ml<=-100),
                     ("-200_to_-299",lambda ml:-300<ml<=-200),
                     ("-300_to_-499",lambda ml:-500<ml<=-300),
                     ("-500_to_-999",lambda ml:-1000<ml<=-500),
                     ("-1000_or_shorter",lambda ml:ml<=-1000),
                     ("positive_or_even",lambda ml:ml>0)]:
        found=[r for r in choices if r["moneyline"] is not None and fn(r["moneyline"])]
        w=sum(x["better_ats_won_su"] for x in found)
        total=sum(x["net"] for x in found)
        print("BUCKET",label,"games",len(found),"SU",w,len(found)-w,
              "net",round(total,2),"ROI",round(total/len(found),2) if found else "N/A")

if __name__=="__main__":main()
