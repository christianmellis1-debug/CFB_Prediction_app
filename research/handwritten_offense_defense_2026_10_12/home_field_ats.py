"""ATS evaluation of handwritten 40/25/15/10/10 ratings + home advantage.

Join EXACT 2022-26 previously evaluated games to historical ESPN-derived spread
dataset on ESPN game_id AND season. Only a valid non-default, non-injected
spread with known orientation and source qualifies. Exclude ambiguous / missing
line or incomplete outcome; report coverage and push totals explicitly.

This is retrospective, sources can be revised/late-captured; NOT necessarily a
frozen pregame closing price and NO payout or positive-ROI claim is made.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import math
from urllib.request import urlopen

import numpy as np
import pandas as pd

from research.handwritten_offense_defense_2026_10_12.home_field import venue_for_season
from research.handwritten_offense_defense_2026_10_12.run import year_inputs

OUT=Path("research/handwritten_offense_defense_2026_10_12/home_field_ats_results.json")
DETAILS=Path("research/handwritten_offense_defense_2026_10_12/home_field_ats_games.csv")
BETTING_ASSET=("https://github.com/sportsdataverse/sportsdataverse-data/"
               "releases/download/espn_cfb_betting/betting_{year}.csv")
SOURCE_ALLOW={"summary_pickcenter","core_odds_api"}
EPS=1e-8


def historical_lines(year):
    """Read ESPN game-scoped line, verify provider provenance and home sign."""
    with urlopen(BETTING_ASSET.format(year=year),timeout=100) as stream:
        odds=pd.read_csv(stream,low_memory=False)
    needed={"game_id","season","week","game_spread_available",
            "home_team_spread","odds_source"}
    missing=needed-set(odds)
    if missing:
        raise ValueError(f"{year}: historical betting data missing {sorted(missing)}; found {list(odds)}")
    total=len(odds)
    for k in ("game_id","season","week","home_team_spread"):
        odds[k]=pd.to_numeric(odds[k],errors="coerce")
    if odds[["game_id","season"]].duplicated(keep=False).any():
        raise ValueError(f"{year}: duplicate ESPN game ID/season betting rows")
    valid_ids=odds.game_id.notna()&odds.game_id.mod(1).eq(0)
    odds=odds[valid_ids & odds.season.eq(year)].copy()
    # Prevent a string "false" from being treated as truthy.
    available=odds.game_spread_available.astype(str).str.strip().str.lower().isin(("true","t","1","1.0","yes"))
    sources=odds.odds_source.astype(str).str.strip().str.lower()
    clean=odds.home_team_spread.notna() & np.isfinite(odds.home_team_spread)
    clean &= odds.home_team_spread.abs().le(100)
    clean &= odds.week.notna()&odds.week.mod(1).eq(0)
    good=available&sources.isin(SOURCE_ALLOW)&clean
    dropped={
        "all_rows":int(total),
        "target_year_unique_id_rows":len(odds),
        "spread_available":int(available.sum()),
        "source_counts":{str(k):int(v) for k,v in sources.value_counts(dropna=False).items()},
        "valid_source_and_spread_rows":int(good.sum()),
        "missing_or_invalid_source_rows":int((~good).sum()),
    }
    subset=odds[good].copy()
    subset["game_id"]=subset.game_id.astype("int64").astype(str)
    subset["season"]=subset.season.astype(int)
    subset["week"]=subset.week.astype(int)
    subset["odds_source"]=sources[good]
    if subset.game_id.duplicated().any():
        raise ValueError(f"{year}: duplicate valid line IDs")
    return subset,dropped


def to_game_rows(year):
    frame,_=year_inputs(year)
    frame=venue_for_season(frame,year)
    raw,coverage=historical_lines(year)
    keys=["game_id","season","week","home_team_spread","odds_source"]
    # Additional identity validation when dataset includes these fields.
    for field in ("home_id","away_id"):
        if field in raw:
            keys.append(field)
    if "status" in raw:
        keys.append("status")
    joined=frame.merge(raw[keys],on=["game_id","season","week"],
                      how="left",validate="one_to_one",indicator=True,
                      suffixes=("","_odds"))
    # Preserve missing line games solely as coverage counts, never as picks.
    had=joined["_merge"].eq("both")
    if any(z in joined for z in ("home_id","away_id")):
        from research.run_offense_defense_2026_10_12.run import prepare_schedule
        sched=prepare_schedule(year).drop_duplicates("game_id")
        ids=sched[["game_id","home_id","away_id"]].copy()
        ids["game_id"]=ids.game_id.astype(int).astype(str)
        ids=ids.rename(columns={"home_id":"schedule_home_id","away_id":"schedule_away_id"})
        joined=joined.merge(ids,on="game_id",how="left",validate="many_to_one")
        for side in ("home","away"):
            col=side+"_id"
            if col in joined:
                observed=pd.to_numeric(joined[col],errors="coerce")
                expected=pd.to_numeric(joined["schedule_"+col],errors="coerce")
                had &= observed.notna()&expected.notna()&observed.eq(expected)
    if "status" in joined:
        status=joined["status"].astype(str).str.upper()
        had &= status.isin(("STATUS_FINAL","STATUS_FINAL_OVERTIME"))
    had &= joined.home_team_spread.notna()
    line_count=int(had.sum())
    eligible=joined.loc[had].copy()
    if not eligible.empty:
        spread=eligible.home_team_spread.to_numpy(dtype=float)
        if not np.isfinite(spread).all():
            raise AssertionError("Nonfinite qualified line")
        margin=eligible.home_win.to_numpy() # outcome identity guard below
        # Scores are retrieved from the SAME schedule used in the original unit test.
        from research.run_offense_defense_2026_10_12.run import prepare_schedule
        schedule=prepare_schedule(year)
        score=schedule[["game_id","home_points","away_points"]].copy()
        score["game_id"]=score.game_id.astype(int).astype(str)
        score=score.drop_duplicates("game_id",keep=False)
        eligible=eligible.merge(score,on="game_id",how="left",validate="one_to_one")
        hp=eligible.home_points.to_numpy(dtype=float)
        ap=eligible.away_points.to_numpy(dtype=float)
        if not np.isfinite(hp).all() or not np.isfinite(ap).all():
            raise ValueError(f"{year}: settled game missing score")
        if not np.all((hp>ap).astype(int)==eligible.home_win.to_numpy(dtype=int)):
            raise AssertionError(f"{year}: outcome mismatch")
        margin=hp-ap+eligible.home_team_spread.to_numpy(dtype=float)
        eligible["ats_home_result"]=np.where(margin>EPS,1,np.where(margin< -EPS,-1,0))
        eligible["ats_margin"]=margin
        eligible["ats_push"]=np.abs(margin)<=EPS
        eligible["v15_side"]=np.where(eligible.baseline_probability.to_numpy()>=.5,1,-1)
        eligible["handwritten_side"]=np.where(eligible.custom_probability.to_numpy()>=.5,1,-1)
        eligible["off_side"]=np.where(eligible.proposed_offense_edge.to_numpy()>EPS,1,
                                  np.where(eligible.proposed_offense_edge.to_numpy()< -EPS,-1,0))
        eligible["def_side"]=np.where(eligible.proposed_defense_edge.to_numpy()>EPS,1,
                                  np.where(eligible.proposed_defense_edge.to_numpy()< -EPS,-1,0))
        eligible["both_side"]=np.where((eligible.off_side==eligible.def_side)&eligible.off_side.ne(0),
                                      eligible.off_side,0)
        eligible["v15_both_confirmed"]=(eligible.both_side==eligible.v15_side)
        eligible["v15_both_conflicted"]=(eligible.both_side==-eligible.v15_side)
        eligible["handwritten_both_conflicted"]=(eligible.both_side==-eligible.handwritten_side)
        eligible["neutral_site"]=eligible.neutral_site.astype(bool)
    analysis={
        "same_games_with_any_outcome":len(frame),
        "valid_spreads_matching_same_season_week_game":line_count,
        "unpriced_eligible_games":len(frame)-line_count,
        "line_coverage":round(line_count/len(frame),5) if len(frame) else None,
        "source":coverage
    }
    return eligible,analysis


def grade(mask,side,ats):
    # All eligible pushes are excluded from decisions; never count as losses.
    have=mask & (side!=0)
    n=int(have.sum())
    push=int((have&(ats==0)).sum())
    valid=have&(ats!=0)
    wins=int((valid&(ats==side)).sum())
    losses=int((valid&(ats!=side)).sum())
    assert wins+losses+push==n
    return {"qualified":n,"wins":wins,"losses":losses,"pushes":push,
            "decisions":wins+losses,
            "ats_win_pct":round(wins/(wins+losses),6) if wins+losses else None}


def cohort_breakdown(frame):
    if frame.empty:
        return {}
    neutral=frame.neutral_site.to_numpy(dtype=bool)
    home=~neutral
    b=frame.both_side.to_numpy(dtype=int)
    o=frame.off_side.to_numpy(dtype=int)
    d=frame.def_side.to_numpy(dtype=int)
    v15=frame.v15_side.to_numpy(dtype=int)
    handwritten=frame.handwritten_side.to_numpy(dtype=int)
    ats=frame.ats_home_result.to_numpy(dtype=int)
    n=len(frame)
    everything=np.ones(n,dtype=bool)
    both_home=(b==1)&home
    both_away=(b==-1)&home
    both_neutral=(b!=0)&neutral
    split=(o!=0)&(d!=0)&(o==-d)
    only_home=home&(o==1)&(d==1)
    both_conflict=(b!=0)&(b!=v15)
    both_agree=(b!=0)&(b==v15)
    winner_choice=np.where(b!=0,b,v15)
    return {
        "matched_games":n,
        "spread_sources":{str(k):int(v) for k,v in frame.odds_source.value_counts().items()},
        "home_team_all_nonneutral":grade(home,np.ones(n,int),ats),
        "home_team_both_edges":grade(both_home,np.ones(n,int),ats),
        "away_team_both_edges":grade(both_away,-np.ones(n,int),ats),
        "both_edges_neutral":grade(both_neutral,b,ats),
        "both_edges_any":grade(b!=0,b,ats),
        "both_edges_vs_original_v15":{
            "v15_on_same_both_games":grade(b!=0,v15,ats),
            "handwritten_both_on_same_both_games":grade(b!=0,b,ats),
            "agree_with_v15":grade(both_agree,v15,ats),
            "conflict_with_v15_original":grade(both_conflict,v15,ats),
            "conflict_with_v15_follow_both":grade(both_conflict,b,ats),
            "home_both_conflict_v15":grade(both_home&(v15==-1),b,ats),
            "away_both_conflict_v15":grade(both_away&(v15==1),b,ats),
        },
        "split_edges":{
            "original_v15":grade(split,v15,ats),
            "higher_offense":grade(split,o,ats),
            "higher_defense":grade(split,d,ats),
        },
        "v15_all_graded":grade(everything,v15,ats),
        "handwritten_full_model_all_graded":grade(everything,handwritten,ats),
        "hypothetical_both_override_v15_all":grade(everything,winner_choice,ats),
    }


def main():
    seasons,cohorts={},[]
    for yr in range(2022,2027):
        frame,coverage=to_game_rows(yr)
        years=str(yr)
        seasons[years]={"coverage":coverage,"ats":cohort_breakdown(frame)}
        if not frame.empty:
            cohort=frame.copy()
            cohort["season"]=yr
            cohorts.append(cohort)
    if not cohorts:
        raise ValueError("No verified point spreads join to eligible handwritten game cohort")
    all_games=pd.concat(cohorts,ignore_index=True)
    if all_games.duplicated(["season","game_id"]).any():
        raise AssertionError("Cross-year unique ESPN game IDs violated")
    combined=cohort_breakdown(all_games)
    summary={
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "hypothesis":"User-written 40/25/15/10/10 offense+defense; home versus away double-advantage ATS 2022-2026 W6",
        "spread_dataset":"sportsdataverse ESPN CFB betting releases espn_cfb_betting betting_{season}.csv",
        "valid_odds_sources":sorted(SOURCE_ALLOW),
        "qualifications":"Only game_spread_available true, finite home_team_spread, known source, exact ESPN game ID + season + week. Exclude source=default/injected. Require finished regulation game score from same schedule and valid team IDs where provided.",
        "seasons":seasons,
        "combined":combined,
        "total_original_cohort":sum(s["coverage"]["same_games_with_any_outcome"] for s in seasons.values()),
        "total_matched_spreads":len(all_games),
        "missing_spreads":sum(s["coverage"]["unpriced_eligible_games"] for s in seasons.values()),
        "limitations":[
            "Historical released odds may be late-captured, mutable or reconstructed; this is NOT a frozen verified pregame odds snapshot.",
            "Source selection is ESPN summary/core provider, NOT necessarily DraftKings. No provider-specific claim.",
            "Spread-specific positive win rate does not imply positive ROI; wager price/juice unavailable.",
            "ATS push = team final score margin plus corresponding spread exactly zero; exclude push from ATS win percentage.",
            "The same games appear in the historical 2022-2026 offense/defense/home win study; weeks 1-2 and games with incomplete pregame box stats are omitted.",
            "Conditional home both advantages have a different game selection and favorite/spread distribution from away both; do NOT infer a causal venue effect.",
            "Retrospective research only; all input seasons previously examined. To validate future performance use prospective pregame-locked lines and model outputs.",
            "No live app, model weights, value tiers or four-model prospectively frozen archive changed."
        ],
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(summary,indent=2,allow_nan=False,default=lambda x:x.item() if isinstance(x,np.generic) else str(x))+"\n")
    export_cols=[x for x in (
        "season","week","game_id","away","home","neutral_site",
        "home_points","away_points","home_team_spread","odds_source",
        "ats_margin","ats_home_result","proposed_offense_edge",
        "proposed_defense_edge","both_side","baseline_probability",
        "custom_probability","v15_side","handwritten_side")
                 if x in all_games]
    all_games[export_cols].sort_values(["season","week","game_id"]).to_csv(DETAILS,index=False)
    print(json.dumps({
        "coverage":{yr:info["coverage"] for yr,info in seasons.items()},
        "per_year":{yr:info["ats"] for yr,info in seasons.items()},
        "combined":combined,
    },indent=2))


if __name__=="__main__":
    main()
