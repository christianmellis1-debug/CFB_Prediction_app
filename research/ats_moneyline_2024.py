"""Reproduce the 2025 experiment in 2024: 7+ pregame net ATS gap, ML -100 to -300."""
from concurrent.futures import ThreadPoolExecutor, as_completed

from ats_discrepancy_2024_2025 import season_data, run
from ats_moneyline_2025 import get_payload, extract_price, american_profit, implied_prob

def main():
    rows=run(2024,season_data(2024))
    matches=[r for r in rows if r["net_gap"]>=7]
    print("SEASON 2024 TOTAL 7+ NET_GAP",len(matches))
    print("SEASON 2024 ATS STRONGER TEAM FAVORED BY SPREAD",sum(r["stronger_line"] is not None and r["stronger_line"]<0 for r in matches))
    fetched={}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for fut in as_completed([pool.submit(get_payload,r["game_id"]) for r in matches]):
            gid,payload,error=fut.result()
            fetched[gid]=(payload,error)
    results=[]
    for r in matches:
        payload,error=fetched[r["game_id"]]
        items=payload.get("items",[]) if isinstance(payload,dict) else []
        candidates=[]
        for item in items:
            prov=item.get("provider") or {}
            if not isinstance(prov,dict):prov={}
            price,snapshot=extract_price(item.get("homeTeamOdds") if r["stronger_is_home"] else item.get("awayTeamOdds"))
            if price is None:continue
            provider=str(prov.get("name") or "Unknown")
            try:priority=int(prov.get("priority",999))
            except (ValueError,TypeError):priority=999
            candidates.append((provider,priority,price,snapshot))
        candidates.sort(key=lambda c:(0 if c[0].lower().replace(" ","")=="draftkings" else 1,
                                      0 if c[3]=="close" else 1,
                                      c[1],c[0]))
        chosen=candidates[0] if candidates else None
        if chosen:
            provider,_,ml,snap=chosen
        else:
            provider,ml,snap="N/A",None,"missing"
        qualifies=(r["stronger_line"] is not None and r["stronger_line"]<0
                   and ml is not None and -300<=ml<=-100 and snap=="close")
        outcome="W" if r["better_ats_won_su"] else "L"
        profit=(american_profit(ml) if outcome=="W" else -100) if qualifies else None
        results.append({**r,"ml":ml,"provider":provider,"snapshot":snap,"qualifies":qualifies,"profit":profit,
                        "implied":implied_prob(ml) if qualifies else None})
        print("CHECK2024|"+"|".join(map(str,[
            r["week"],r["game_id"],r["net_gap"],r["favored_by_ats"],r["matchup"],
            r["stronger_line"],ml,provider,snap,outcome,
            "YES" if qualifies else "NO",
            "ERROR "+error if error else "",
        ])))
    selection=[x for x in results if x["qualifies"]]
    print("SELECTED2024",len(selection))
    for x in sorted(selection,key=lambda x:(x["week"],x["game_id"])):
        hp=x["home_points"]; ap=x["away_points"]
        score=f"{hp}-{ap}" if x["stronger_is_home"] else f"{ap}-{hp}"
        print("GAME2024|"+"|".join(map(str,[
            x["week"],x["net_gap"],x["favored_by_ats"],x["favored_pre_ATS"],
            x["matchup"],x["ml"],x["provider"],score,
            "W" if x["better_ats_won_su"] else "L",
            "W" if x["better_ats_covered"]==1 else "L" if x["better_ats_covered"]==0 else "P",
            f"{x['profit']:+.2f}",x["game_id"],
        ])))
    wins=sum(x["better_ats_won_su"] for x in selection)
    profit=sum(x["profit"] for x in selection)
    expected=sum(x["implied"] for x in selection)
    print("SUMMARY2024", "games",len(selection),"wins",wins,"losses",len(selection)-wins,
          "net_100",round(profit,2),"roi_pct",round(profit/len(selection),2) if selection else "N/A",
          "implied_expected_wins",round(expected,3),"expected_win_pct",round(expected/len(selection)*100,2) if selection else "N/A")
    for label,lo,hi in [("-100_to_-199",-199,-100),("-200_to_-300",-300,-200),("inclusive_total",-300,-100)]:
        subset=[x for x in selection if lo<=x["ml"]<=hi]
        p=sum(x["profit"] for x in subset)
        print("BUCKET2024",label,len(subset),sum(x["better_ats_won_su"] for x in subset),
              len(subset)-sum(x["better_ats_won_su"] for x in subset),round(p,2),
              round(p/len(subset),2) if subset else None)
    print("MISSING2024",sum(x["ml"] is None for x in results),
          "fetch_errors",sum(fetched[x["game_id"]][1] is not None for x in matches))

if __name__=="__main__":
    main()
