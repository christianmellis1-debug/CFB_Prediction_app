"""Prospective 2026 ATS Advantage candidate scan: 7+ net ATS disparity and ML -200 to -300.

Run using public ESPN schedule/odds, frozen at the stated user request time.
This does not change Saturday Forecast production or previous research.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from ats_discrepancy_2024_2025 import fetch_csv, truth
from ats_moneyline_2025 import get_payload, extract_price, implied_prob

NOW = pd.Timestamp("2026-10-14T15:36:00Z")
HORIZON = pd.Timestamp("2026-10-21T05:00:00Z")
SCHEDULE = "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_2026.csv"
BETTING = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_betting/betting_2026.csv"

def main():
    sched = fetch_csv(SCHEDULE).copy()
    market = fetch_csv(BETTING).copy()
    print("DIAG", "schedule",sched.shape,"market",market.shape,"schedule_cols",list(sched.columns),"market_cols",list(market.columns))
    for c in ["game_id","week","home_id","away_id","home_points","away_points"]:
        sched[c] = pd.to_numeric(sched[c],errors="coerce")
    sched["kickoff"] = pd.to_datetime(sched["start_date"],errors="coerce",utc=True)
    sched=sched[(sched["season_type"].astype(str).str.lower()=="regular") &
                (sched["home_division"].astype(str).str.lower()=="fbs") &
                (sched["away_division"].astype(str).str.lower()=="fbs")].copy()
    sched=sched.dropna(subset=["game_id","week","home_id","away_id"]).drop_duplicates("game_id")
    upcoming=sched[(sched["kickoff"]>=NOW)&(sched["kickoff"]<HORIZON)&~truth(sched["completed"])].sort_values(["kickoff","game_id"]).copy()
    past=sched[(sched["kickoff"]<NOW)&truth(sched["completed"])].copy()
    print("DIAG", "schedule_fbs",len(sched),"completed_fbs",len(past),"upcoming_fbs",len(upcoming),"weeks",sorted(upcoming.week.unique().tolist()))
    if upcoming.empty: return
    market["game_id"]=pd.to_numeric(market["game_id"],errors="coerce")
    market["home_team_spread"]=pd.to_numeric(market["home_team_spread"],errors="coerce")
    market=market[truth(market["game_spread_available"]) & market["home_team_spread"].notna()]
    if "odds_source" in market: market=market[~market["odds_source"].astype(str).str.lower().isin(["default","injected"])]
    market=market.drop_duplicates("game_id")
    past=past.merge(market[["game_id","home_team_spread"]],how="left",on="game_id",validate="one_to_one")
    past=past.dropna(subset=["home_points","away_points"])
    print("DIAG", "past_spread_coverage",past["home_team_spread"].notna().sum(),len(past),"missing",len(past)-past["home_team_spread"].notna().sum())
    latestweek=int(upcoming["week"].min())
    past=past[past["week"]<latestweek]
    print("DIAG","latestweek",latestweek,"priorweek_games",len(past))
    rec={}
    def ensure(team): return rec.setdefault(int(team),{"w":0,"l":0,"p":0,"played":0,"graded":0})
    for _,g in past.iterrows():
        h,a=ensure(g.home_id),ensure(g.away_id)
        h["played"]+=1;a["played"]+=1
        if pd.isna(g.home_team_spread):continue
        net=float(g.home_points)-float(g.away_points)+float(g.home_team_spread)
        if net>0: h["w"]+=1;a["l"]+=1
        elif net<0: h["l"]+=1;a["w"]+=1
        else: h["p"]+=1;a["p"]+=1
        h["graded"]+=1;a["graded"]+=1
    rows=[]
    for _,g in upcoming.iterrows():
        a=ensure(g.away_id)
        h=ensure(g.home_id)
        neta=a["w"]-a["l"];neth=h["w"]-h["l"]
        gap=abs(neta-neth)
        side="home" if neth>neta else "away" if neta>neth else None
        rows.append(dict(
            id=int(g.game_id),week=int(g.week),kickoff=g.kickoff.isoformat(),
            home=str(g.home_team),away=str(g.away_team),gap=gap,
            side=side, strong=(str(g.home_team) if side=="home" else str(g.away_team) if side=="away" else "-"),
            weak=(str(g.away_team) if side=="home" else str(g.home_team) if side=="away" else "-"),
            stronger=(dict(h) if side=="home" else dict(a) if side=="away" else {}),
            weaker=(dict(a) if side=="home" else dict(h) if side=="away" else {}),
        ))
    print("DIAG","count_gaps_7plus",sum(x["gap"]>=7 for x in rows),
          "count_gaps_6plus",sum(x["gap"]>=6 for x in rows),"count_gaps_5plus",sum(x["gap"]>=5 for x in rows))
    # Check all slate odds so we can catch market candidates that are close
    # to qualifying on ATS discrepancy.
    fetched={}
    with ThreadPoolExecutor(max_workers=8) as pool:
        future=[pool.submit(get_payload,r["id"]) for r in rows]
        for f in as_completed(future):
            gid,payload,error=f.result()
            fetched[gid]=(payload,error)
    for r in rows:
        payload,error=fetched[r["id"]]
        choices=[]
        for item in payload.get("items",[]) if isinstance(payload,dict) else []:
            name=str((item.get("provider") or {}).get("name") or "Unknown")
            for side in ["home","away"]:
                price,snap=extract_price(item.get(side+"TeamOdds"))
                if price is not None:
                    choices.append((side,name,price,snap))
        # Prefer ESPN BET or DraftKings pregame/closing quotes over in-game live odds.
        quotes={}
        for side in ["home","away"]:
            side_quotes=[x for x in choices if x[0]==side and "Live Odds" not in x[1]]
            side_quotes.sort(key=lambda x:(0 if x[3]=="close" else 1,0 if x[1]=="ESPN BET" else 1 if x[1]=="DraftKings" else 2))
            if side_quotes:quotes[side]=side_quotes[0]
        strong_ml=quotes.get(r["side"])
        if strong_ml:
            ml=strong_ml[2];prov=strong_ml[1];snap=strong_ml[3]
        else: ml=None;prov="-";snap="-"
        # Avoid treating a start-of-game/last-play live market as pregame prices
        # by flagging any non-close snapshot explicitly.
        qual=r["gap"]>=7 and ml is not None and -300<=ml<=-200 and snap=="close"
        if qual:label="QUALIFIES"
        elif r["gap"]>=7:label="ATS_GAP_ONLY"
        elif ml is not None and -300<=ml<=-200 and r["gap"]>=4:label="NEAR_ATS_GAP"
        else:label="OTHER"
        strongrec=r["stronger"];weakrec=r["weaker"]
        fmt=lambda x: f"{x['w']}-{x['l']}-{x['p']} graded {x['graded']}/{x['played']}"
        print("CANDIDATE2026|"+ "|".join(map(str,[
            label,r["week"],r["kickoff"],r["gap"],r["strong"],fmt(strongrec) if strongrec else "TIED",
            r["weak"],fmt(weakrec) if weakrec else "TIED",
            f"{ml:+d}" if ml is not None else "N/A",prov,snap,
            r["away"]+" at "+r["home"],r["id"],"fetch_error "+error if error else ""
        ])))
    print("END_2026")

if __name__=="__main__":main()
