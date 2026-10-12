"""Historical fixed-rule A/B study: same-group handwritten double edge + home favorite.

A: any verified negative home-team point spread.
B: only negative home spread > -10, e.g. -9.5, -7, -3.

Both exclude P4/P4 with 0.50 <= min(off_edge,def_edge) < 0.75,
retain G6/G6 in the same magnitude band, and use pre-set
conference policy, no post-result parameter fitting.

All classifications and scores matched on ESPN game id, season, week;
historical ESPN betting feed is retrospective, not timestamped pregame odds.
"""
from pathlib import Path
from datetime import datetime,timezone
import json
import math
import numpy as np
import pandas as pd

from research.handwritten_offense_defense_2026_10_12.run import (
    year_inputs,prepare_schedule
)
from research.handwritten_offense_defense_2026_10_12.home_field_ats import historical_lines
from research.handwritten_offense_defense_2026_10_12.same_group import group

ROOT=Path("research/handwritten_offense_defense_2026_10_12")
RESULT=ROOT/"favorites_two_test_results.json"
GAMES=ROOT/"favorites_two_test_games.csv"
EPS=1e-10

def collect(year):
    original,_=year_inputs(year)
    schedule=prepare_schedule(year)
    if schedule.game_id.duplicated(keep=False).any():
        raise AssertionError(f"{year}: duplicated schedule id")
    schedule=schedule.copy()
    schedule["game_id"]=schedule.game_id.astype("int64").astype(str)
    info=schedule[["game_id","season","week","home_team","away_team",
                   "home_conference","away_conference","neutral_site"]].copy()
    original=original.merge(info,on=["game_id","season","week"],
                            how="left",validate="one_to_one",indicator=True)
    if not original["_merge"].eq("both").all():
        raise AssertionError(f"{year}: missing schedule join")
    if not original.home.eq(original.home_team).all() or not original.away.eq(original.away_team).all():
        raise AssertionError(f"{year}: invalid source identities")
    original["home_group"]=[group(c,t,year) for c,t in
                         zip(original.home_conference,original.home)]
    original["away_group"]=[group(c,t,year) for c,t in
                         zip(original.away_conference,original.away)]
    original["same_group"]=original.home_group.notna() & original.home_group.eq(original.away_group)
    original["min_magnitude"]=np.minimum(original.proposed_offense_edge,
                                        original.proposed_defense_edge)
    original["double_home_edge"]=(original.proposed_offense_edge.gt(EPS)&
                                  original.proposed_defense_edge.gt(EPS)&
                                  ~original.neutral_site.astype(bool))
    original["excluded_p4_midrange"]=(original.home_group.eq("P4")&
                                     original.min_magnitude.ge(.5)&
                                     original.min_magnitude.lt(.75))
    source,coverage=historical_lines(year)
    if "home_id" in source.columns or "away_id" in source.columns:
        extra_cols=["game_id","home_id","away_id"]
        identity=schedule[extra_cols].rename(columns={"home_id":"verified_home_id",
                                                       "away_id":"verified_away_id"})
        source=source.merge(identity,on="game_id",how="left",validate="one_to_one")
        for side in ("home","away"):
            if side+"_id" in source.columns:
                actual=pd.to_numeric(source[side+"_id"],errors="coerce")
                expected=pd.to_numeric(source["verified_"+side+"_id"],errors="coerce")
                source=source.loc[actual.eq(expected)&actual.notna()&expected.notna()]
    if "status" in source.columns:
        source=source.loc[source.status.astype(str).str.upper().isin(
            ("STATUS_FINAL","STATUS_FINAL_OVERTIME"))]
    frame=original.merge(source[["game_id","season","week","home_team_spread","odds_source"]],
                         on=["game_id","season","week"],how="left",
                         validate="one_to_one",indicator="_matched_odds")
    frame["has_verified_spread"]=frame["_matched_odds"].eq("both")&frame.home_team_spread.notna()
    frame["same_group_home_both"]=frame.same_group&frame.double_home_edge
    frame["rule_without_odds"]=frame.same_group_home_both&~frame.excluded_p4_midrange
    frame["A"]=frame.rule_without_odds&frame.has_verified_spread&frame.home_team_spread.lt(0)
    frame["B"]=frame["A"]&frame.home_team_spread.gt(-10)
    frame["A_heavy"]=frame["A"]&~frame["B"]
    assert not (frame["B"]&~frame["A"]).any()
    assert not (frame["A"]&frame.excluded_p4_midrange).any()
    return frame,coverage

def stats(df):
    n=len(df);w=int(df.home_win.sum())
    return {"games":n,"wins":w,"losses":n-w,
            "win_pct":round(w/n,6) if n else None,
            "mean_spread":round(float(df.home_team_spread.mean()),3) if n else None}

def summary(df):
    d={}
    for col in ("A","B","A_heavy"):
        selected=df[df[col]]
        d[col]=stats(selected)
        d[col]["by_group"]={s:stats(selected[selected.home_group.eq(s)])
                            for s in ("P4","G6")}
        bins={}
        for lower,upper,label in ((0,.25,"0–0.24"),(.25,.5,"0.25–0.49"),
                                  (.5,.75,"0.50–0.74"),(.75,1,"0.75–0.99"),
                                  (1,np.inf,"1.00+")):
            group_=selected[selected.min_magnitude.ge(lower)&selected.min_magnitude.lt(upper)]
            bins[label]=stats(group_)
        d[col]["by_magnitude"]=bins
    base=df[df.rule_without_odds]
    d["no_odds_qualifying_games"]=len(base)
    d["missing_verified_spread_in_qualifying_games"]=int((~base.has_verified_spread).sum())
    d["home_underdogs_or_pickem_in_qualifying_games"]=int(
        (base.has_verified_spread & base.home_team_spread.ge(0)).sum())
    return d

def main():
    seasons={}
    all_frames=[]
    for year in (2023,2024,2025,2026):
        data,coverage=collect(year)
        all_frames.append(data)
        seasons[str(year)]={"tests":summary(data),"betting_source":coverage}
    all_=pd.concat(all_frames,ignore_index=True)
    last=all_[(all_.season.eq(2026))&all_.week.between(3,6)]
    if stats(last[last["A"]])["games"]!=48 or stats(last[last["A"]])["wins"]!=40:
        raise AssertionError("2026 A must reproduce previously reported 40-8 / 48 games")
    if stats(last[last["B"]])["games"]!=19 or stats(last[last["B"]])["wins"]!=15:
        raise AssertionError("2026 B must reproduce previously reported 15-4 / 19 games")
    if stats(last[last["A_heavy"]])["games"]!=29 or stats(last[last["A_heavy"]])["wins"]!=25:
        raise AssertionError("2026 heavy favorite cohort must be 25-4 / 29 games")
    benchmark=all_[all_.season.between(2023,2025)]
    results={
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "fixed_rule":"Home team has BOTH positive custom 40/25/15/10/10 blended offense and defense gap, game nonneutral and strictly P4/P4 or G6/G6, no P4/P4 if 0.50 <= smaller advantage <0.75, home team must be favorite with a verified negative home spread.",
        "test_A":"All favorite spreads strictly less than zero, including -10 and more negative",
        "test_B":"Only home favorite spreads strictly greater than -10 and less than 0, such as -9.5 to -0.5; -10 excluded",
        "betting_lines":"Sportsdataverse archive of ESPN CFB betting odds: game id, season, week matched; verified odds_source not default/injected",
        "seasons":seasons,
        "2023_to_2025":summary(benchmark),
        "2026_w3_to_w6":summary(last),
        "2023_to_2026":summary(all_),
        "notes":[
            "2023 to 2025 retrospective test was NOT a clean blind holdout: these historical seasons informed previous explorations; treat as robustness, not independent validation.",
            "No re-estimation or change to original handwritten model ratings or existing app tiers.",
            "The shared favorite/known-odds requirement is required for BOTH tests; without historical spread, games are never counted.",
            "Test B is a strict subset of A; their win rate comparison is observational, not an independent A/B experiment.",
            "Spread data may have been retrospectively archived, revised or captured late; not an immutable pre-kickoff record.",
            "Straight-up win percentages are not ATS records and alone do not measure profitability."
        ]
    }
    RESULT.write_text(json.dumps(results,indent=2,allow_nan=False,default=lambda x:x.item() if isinstance(x,np.generic) else str(x))+"\n")
    qualified=all_[all_["A"]].copy().sort_values(["season","week","game_id"])
    qualified["result"]=np.where(qualified.home_win.eq(1),"W","L")
    qualified["test_A"]=qualified["A"]
    qualified["test_B"]=qualified["B"]
    cols=["season","week","game_id","home","away","home_group","away_group",
          "home_team_spread","min_magnitude","proposed_offense_edge",
          "proposed_defense_edge","result","test_A","test_B","odds_source"]
    qualified[cols].to_csv(GAMES,index=False)
    print(json.dumps({
        "prior_2023_to_2025":results["2023_to_2025"],
        "2026":results["2026_w3_to_w6"],
        "annual":{y:{"A":v["tests"]["A"],"B":v["tests"]["B"],"missing_odds":v["tests"]["missing_verified_spread_in_qualifying_games"]} for y,v in seasons.items()}
    },indent=2))

if __name__=="__main__":
    main()
