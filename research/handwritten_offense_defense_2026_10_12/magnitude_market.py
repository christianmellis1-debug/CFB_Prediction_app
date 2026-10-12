"""Does handwritten offense+defense advantage SIZE improve SU prediction beyond market?

Use the identical 2,826 Week3+ 2022-26 pregame-eligible FBS games used
for handwritten/home-field results. All full-cohort magnitude analyses use
these games. For market comparisons, use only ESPN-derived legitimate spreads
that previously passed source/identity checks; 2022 coverage is tiny.

The primary "both advantages" size is MIN(home offense rating difference,
home defense rating difference), since both must exceed a threshold. Test
prespecified disjoint bins and cumulative thresholds (not distinct samples).
For a fair favorite comparison, stratify on season+spread bucket, excluding
strata with zero alternative home favorites; report precisely how many
games are actually comparable and never assert causality.
"""
import json
from datetime import datetime,timezone
from pathlib import Path
import math
import numpy as np
import pandas as pd

from research.handwritten_offense_defense_2026_10_12.run import year_inputs
from research.handwritten_offense_defense_2026_10_12.home_field import venue_for_season

ROOT=Path("research/handwritten_offense_defense_2026_10_12")
RESULT=ROOT/"magnitude_market_results.json"
DETAIL=ROOT/"magnitude_market_games_2026.csv"
PRICED=ROOT/"home_field_ats_games.csv"
EPS=1e-10

MAGNITUDE_BINS=((0.,.25),(0.25,.50),(.50,.75),(.75,1.0),(1.0,1.5),(1.5,None))
THRESHOLDS=(0.,.25,.50,.75,1.,1.5)
SPREAD_BINS=((-100.,-21.),(-21.,-14.),(-14.,-7.),(-7.,0.))


def magnitude_bucket(x):
    for lo,hi in MAGNITUDE_BINS:
        if x>=lo and (hi is None or x<hi):
            return f"{lo:g}+" if hi is None else f"{lo:g}–{hi:g}"
    return "not_both"


def spread_bucket(x):
    # Home favorite only. A +3 home line is not a home favorite.
    if x>=0:
        return "not_home_favorite"
    if x<=-21:
        return "21+ point favorite"
    if x<=-14:
        return "14–20.5 point favorite"
    if x<=-7:
        return "7–13.5 point favorite"
    return "Under 7 point favorite"


def stats(data,mask):
    df=data.loc[mask]
    count=len(df)
    wins=int((df.home_win==1).sum())
    return {
        "games":count,
        "wins":wins,
        "losses":count-wins,
        "su_win_rate":round(wins/count,6) if count else None,
        "mean_home_spread":round(float(df.home_team_spread.mean()),3)
                          if count and df.home_team_spread.notna().all() else None,
        "mean_off_edge":round(float(df.proposed_offense_edge.mean()),4) if count else None,
        "mean_def_edge":round(float(df.proposed_defense_edge.mean()),4) if count else None,
        "mean_min_edge":round(float(df.min_advantage.mean()),4) if count else None
    }


def magnitude_groups(data):
    """All pregame eligible non-neutral home double-edge games, lines optional."""
    good=(~data.neutral_site)&(data.proposed_offense_edge>EPS)&(data.proposed_defense_edge>EPS)
    selected=data.loc[good].copy()
    result={
        "total":stats(data,good),
        "magnitude_definition":"Minimum of positive offense and defense blended standard-rating gaps, home minus away.",
        "nonoverlapping_bins":{},
        "cumulative_minimum_thresholds":{},
    }
    for lo,hi in MAGNITUDE_BINS:
        name=magnitude_bucket(lo)
        cond=(selected.min_advantage>=lo)&(selected.min_advantage<hi if hi is not None else True)
        result["nonoverlapping_bins"][name]=stats(selected,cond)
    for t in THRESHOLDS:
        result["cumulative_minimum_thresholds"][str(t)]=stats(selected,selected.min_advantage>=t)
    assert sum(x["games"] for x in result["nonoverlapping_bins"].values())==len(selected)
    return result


def market_favorites_comparison(data):
    """Compare same-year spread classes and apply selected case mix to controls.

    The final standardized benchmark is computed ONLY on common-support
    year/bucket strata. Comparators are different games, not random pairs.
    """
    usable=data[(~data.neutral_site)&data.home_team_spread.notna()
                &(data.home_team_spread<0)].copy()
    usable["spread_bucket"]=usable.home_team_spread.map(spread_bucket)
    usable["both"]=((usable.proposed_offense_edge>EPS)
                    &(usable.proposed_defense_edge>EPS))
    by_bucket={}
    comparable=[]
    excluded=[]
    for (year,spread), group in usable.groupby(["season","spread_bucket"],sort=True):
        both=group[group.both]
        others=group[~group.both]
        if len(both)==0:
            continue
        key=f"{int(year)} : {spread}"
        record={"season":int(year),"spread_bucket":spread,
                "double_advantage":stats(both,pd.Series(True,index=both.index)),
                "other_home_favorites":stats(others,pd.Series(True,index=others.index)),
                "common_support":len(others)>0}
        by_bucket[key]=record
        (comparable if len(others) else excluded).append(record)

    covered=sum(x["double_advantage"]["games"] for x in comparable)
    lost=sum(x["double_advantage"]["games"] for x in excluded)
    if covered:
        selected_wins=sum(x["double_advantage"]["wins"] for x in comparable)
        weighted_controls=sum(
            x["double_advantage"]["games"]*x["other_home_favorites"]["su_win_rate"]
            for x in comparable)/covered
        outcome={
            "matched_by_year_and_spread_bucket_games":covered,
            "selected_both_wins":selected_wins,
            "selected_both_win_rate":round(selected_wins/covered,6),
            "comparator_weighted_win_rate":round(weighted_controls,6),
            "difference_percentage_points":round(
                100*(selected_wins/covered-weighted_controls),3),
            "both_games_with_no_spread_stratum_controls":lost,
            "strata_with_both_and_comparator":len(comparable),
            "strata_with_no_comparator":len(excluded),
        }
    else:
        outcome={"matched_by_year_and_spread_bucket_games":0,
                 "selected_both_win_rate":None,"comparator_weighted_win_rate":None,
                 "both_games_with_no_spread_stratum_controls":lost}
    all_both=usable[usable.both]
    all_other=usable[~usable.both]
    return {
        "qualifying_spread_priced_home_favorites":len(usable),
        "both_home_favorite":stats(all_both,pd.Series(True,index=all_both.index)),
        "other_home_favorites":stats(all_other,pd.Series(True,index=all_other.index)),
        "stratified_comparison":outcome,
        "strata":by_bucket,
        "notes":[
            "Spread buckets are signed home favorite lines: <7, 7–13.5, 14–20.5, 21+ points. Other home favorites lack at least one handwritten edge.",
            "Standardized control rate weights each comparison stratum by the number of both-advantage selections. Only common-support strata are included.",
            "Some very large favorites have no available same-season comparison team; those games are excluded from the standardized comparison and disclosed.",
            "Market spread is only an approximate control for favorite strength and may be a revised retrospective line, not frozen at a known pregame timestamp.",
            "No claim of causality, statistical significance or out-of-sample improvement based solely on these historical descriptive rates."
        ]
    }


def join_verified_lines(full):
    priced=pd.read_csv(PRICED,low_memory=False)
    if priced.duplicated(["season","game_id"]).any():
        raise ValueError("Duplicate validated historical spread identity")
    if not set(["season","week","game_id","home_team_spread","away","home"]).issubset(priced):
        raise ValueError("Expected historical audited spread fields missing")
    priced.game_id=priced.game_id.astype(str)
    full.game_id=full.game_id.astype(str)
    linecols=["season","week","game_id","home_team_spread","home","away",
              "proposed_offense_edge","proposed_defense_edge"]
    matched=full.merge(priced[linecols],on=["season","week","game_id"],
                       how="left",validate="one_to_one",indicator=True,
                       suffixes=("","_priced"))
    verified=matched._merge.eq("both")
    verified &= matched.home.eq(matched.home_priced)&matched.away.eq(matched.away_priced)
    for col in ("proposed_offense_edge","proposed_defense_edge"):
        supplied=pd.to_numeric(matched[col+"_priced"],errors="coerce")
        ours=pd.to_numeric(matched[col],errors="coerce")
        verified &= (supplied-ours).abs().le(1e-9)
    matched.loc[~verified,"home_team_spread"]=np.nan
    matched=matched.drop(columns=[k for k in matched if k.endswith("_priced")]+["_merge"])
    matched["has_verified_spread"]=verified.astype(bool)
    return matched


def subset(frame,year=None,weeks=None):
    target=frame
    if year is not None:
        target=target[target.season.eq(year)]
    if weeks is not None:
        target=target[target.week.isin(weeks)]
    return target.copy()


def main():
    raw=[]
    for year in range(2022,2027):
        frame,quality=year_inputs(year)
        frame=venue_for_season(frame,year)
        frame["season"]=int(year)
        raw.append(frame)
    joined=join_verified_lines(pd.concat(raw,ignore_index=True))
    joined["min_advantage"]=joined[["proposed_offense_edge","proposed_defense_edge"]].min(axis=1)
    joined["spread_bucket"]=joined.home_team_spread.map(
        lambda v: spread_bucket(v) if pd.notna(v) else "unavailable"
    )
    result={
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "question":"How much better does the handwritten offense/defense home team win as BOTH standardized unit gaps increase, relative to similarly favored home teams?",
        "total_pregame_eligible":len(joined),
        "total_verified_spread_games":int(joined.has_verified_spread.sum()),
        "definition":"Only nonneutral HOME team with both positive blended rating gaps. Magnitude is min(offense gap,defense gap), not combined offense+defense or market spread.",
        "all_seasons":magnitude_groups(joined),
        "yearly":{},
        "2026_weeks_4_to_6":{
            "magnitude":magnitude_groups(subset(joined,2026,[4,5,6])),
            "market":market_favorites_comparison(subset(joined,2026,[4,5,6]))
        },
        "market":{
            "2023_2025":market_favorites_comparison(
                subset(joined).loc[joined.season.isin([2023,2024,2025])]),
            "2026_weeks_3_to_6":market_favorites_comparison(subset(joined,2026)),
            "2023_2026":market_favorites_comparison(
                subset(joined).loc[joined.season.isin([2023,2024,2025,2026])]),
        },
        "caveats":[
            "Retrospective tests; the user's exact offense/defense weights and same historical current-season/prior rating blending are preserved; no code changes to the live app.",
            "A high straight-up win rate among very large favorites is expected and does not establish betting value or predictive improvement beyond the market.",
            "Magnitude thresholds are cumulative/overlapping; use nonoverlapping bins for independent descriptive comparisons.",
            "Spread-matched controls are by year and coarse spread group, not randomized or a fully calibrated betting-market win-probability model.",
            "2022 odds have extremely low verified-coverage in source; 2022 remains in pure magnitude summary but cannot provide meaningful spread-matched comparisons.",
            "Earlier-week data and reconstructed model outputs can differ from originally captured pregame records; all seasons have been inspected before, so results aren't pristine forward validation.",
            "Zero-game bins have null meaningful hit rate rather than counting losses.",
            "Results are straight-up and use historical spreads solely for price matching, not ATS grading, and do not estimate positive ROI."
        ]
    }
    for year in range(2022,2027):
        s=subset(joined,year)
        result["yearly"][str(year)]={
            "magnitude":magnitude_groups(s),
            "priced_games":int(s.has_verified_spread.sum()),
            "pregame_eligible":len(s),
        }
    if int(result["2026_weeks_4_to_6"]["magnitude"]["total"]["games"])!=51:
        raise AssertionError("2026 Week4-6 source parity: expected 51 home double-edge selections")
    if int(result["2026_weeks_4_to_6"]["magnitude"]["total"]["wins"])!=39:
        raise AssertionError("2026 Week4-6 source parity: expected 39 correct")
    RESULT.parent.mkdir(parents=True,exist_ok=True)
    RESULT.write_text(json.dumps(result,indent=2,allow_nan=False,
                                 default=lambda x:x.item() if isinstance(x,np.generic) else str(x))+"\n")
    t=subset(joined,2026,[4,5,6])
    t=t[(~t.neutral_site)&(t.proposed_offense_edge>EPS)&(t.proposed_defense_edge>EPS)]
    t=t.copy()
    t["Result"]=np.where(t.home_win.eq(1),"Win","Loss")
    t["Min gap bin"]=t.min_advantage.map(magnitude_bucket)
    cols=["week","game_id","home","away","Result","home_team_spread",
          "proposed_offense_edge","proposed_defense_edge","min_advantage","Min gap bin"]
    t[cols].sort_values(["week","min_advantage"],ascending=[True,False]).to_csv(DETAIL,index=False)
    print(json.dumps({
        "cohort":result["total_pregame_eligible"],
        "wk4to6":result["2026_weeks_4_to_6"],
        "all_seasons":result["all_seasons"],
        "market2023_2025":{k:v for k,v in result["market"]["2023_2025"].items() if k!="strata"},
        "market2026":{k:v for k,v in result["market"]["2026_weeks_3_to_6"].items() if k!="strata"},
    },indent=2))


if __name__=="__main__":
    main()
