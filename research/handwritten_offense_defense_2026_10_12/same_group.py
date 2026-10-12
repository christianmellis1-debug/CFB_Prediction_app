"""Strict season-aware P4/P4 and G6/G6 audit of handwritten home-both rule.

This is a FILTER on exactly the same pregame model ratings used in the 2022-26
handwritten + home-field historical research, never a recalibration or rating
recomputation. It does not limit historical opponent pool for the underlying
efficiency statistics; only evaluated TARGET GAME matchups are filtered.
"""
from pathlib import Path
from datetime import datetime,timezone
import json
import numpy as np
import pandas as pd

from research.handwritten_offense_defense_2026_10_12.run import (
    year_inputs,prepare_schedule
)

ROOT=Path("research/handwritten_offense_defense_2026_10_12")
RESULT=ROOT/"same_group_results.json"
DETAIL=ROOT/"same_group_games_2026.csv"
P4={"ACC","Big Ten","Big 12","SEC"}
G6={"American Athletic","Conference USA","Mid-American","Mountain West","Sun Belt"}
BINS=((0.,.25),(.25,.50),(.50,.75),(.75,1.),(1.,None))
EPS=1e-10


def group(conference,team,year):
    """Fail closed on independent, changed or unknown affiliations.

    2022-2023 Pac-12 is historic P4; 2024-2025 two-team Pac-12 is
    excluded as ambiguous; 2026 Pac-12 is G6 per present app policy.
    """
    name=str(team).strip().casefold()
    if name in {"notre dame","notre dame fighting irish"}:
        return "P4"
    conference=str(conference).strip()
    if conference in P4:
        return "P4"
    if conference in G6:
        return "G6"
    if conference=="Pac-12":
        return "P4" if year<=2023 else "G6" if year>=2026 else None
    return None


def annotate(data, year):
    schedule=prepare_schedule(year)
    if schedule.game_id.duplicated(keep=False).any():
        raise ValueError(f"{year}: duplicate IDs in official game schedule")
    lookup=schedule.set_index(schedule.game_id.astype(int).astype(str))
    rec=[]
    for r in data.itertuples(index=False):
        g=lookup.loc[str(r.game_id)]
        if int(g.week)!=int(r.week):
            raise AssertionError(f"{year}: week mismatch for {r.game_id}")
        if str(g.home_team)!=str(r.home) or str(g.away_team)!=str(r.away):
            raise AssertionError(f"{year}: team identity mismatch for {r.game_id}")
        home=group(g.home_conference,g.home_team,year)
        away=group(g.away_conference,g.away_team,year)
        category=(f"{home} vs {away}" if home and away else "unclassified")
        same=home is not None and home==away
        neutral=bool(g.neutral_site)
        eligible_home_both=(
            not neutral
            and float(r.proposed_offense_edge)>EPS
            and float(r.proposed_defense_edge)>EPS
        )
        rec.append({
            "season":year,"week":int(r.week),"game_id":str(r.game_id),
            "home":str(r.home),"away":str(r.away),
            "home_conference":str(g.home_conference),
            "away_conference":str(g.away_conference),
            "home_group":home,"away_group":away,
            "group_pair":category,"same_group":bool(same),
            "neutral_site":neutral,
            "home_both":bool(eligible_home_both),
            "home_win":int(r.home_win),
            "home_points":float(g.home_points),
            "away_points":float(g.away_points),
            "off_edge":float(r.proposed_offense_edge),
            "def_edge":float(r.proposed_defense_edge),
            "min_edge":float(min(r.proposed_offense_edge,r.proposed_defense_edge))
        })
    return pd.DataFrame(rec)


def wins(data):
    return {"games":len(data),"wins":int(data.home_win.sum()),
            "losses":int(len(data)-data.home_win.sum()),
            "win_pct":round(float(data.home_win.mean()),6) if len(data) else None}


def bands(data):
    out={}
    for lo,hi in BINS:
        label=f"{lo:g}–{hi:g}" if hi is not None else f"{lo:g}+"
        v=data[data.min_edge.ge(lo)]
        if hi is not None:
            v=v[v.min_edge.lt(hi)]
        out[label]=wins(v)
    if sum(row["games"] for row in out.values())!=len(data):
        raise AssertionError("Non-overlapping magnitude bins must sum to filter")
    return out


def block(data):
    home_both=data[data.home_both]
    target=home_both[home_both.same_group]
    p4=target[target.home_group.eq("P4")]
    g6=target[target.home_group.eq("G6")]
    assert len(p4)+len(g6)==len(target)
    return {
        "all_evaluated_games":len(data),
        "home_both_all_pregame_eligible":wins(home_both),
        "same_group_home_both":wins(target),
        "same_group_p4_v_p4":wins(p4),
        "same_group_g6_v_g6":wins(g6),
        "excluded_home_both_mixed_or_unclassified":wins(home_both[~home_both.same_group]),
        "bands_same_group_all":bands(target),
        "bands_p4_v_p4":bands(p4),
        "bands_g6_v_g6":bands(g6),
        "cumulative_same_group":{
            str(c):wins(target[target.min_edge.ge(c)]) for c in (.25,.50,.75,1.0)
        },
        "excluded_categories":{
            str(k):wins(v)
            for k,v in home_both[~home_both.same_group].groupby("group_pair")
        }
    }


def main():
    years={}
    tables=[]
    for year in (2022,2023,2024,2025,2026):
        data,_=year_inputs(year)
        enriched=annotate(data,year)
        years[str(year)]=block(enriched)
        tables.append(enriched)
    all_=pd.concat(tables,ignore_index=True)
    recent=all_[(all_.season.eq(2026)) & (all_.week.between(3,6))]
    result={
        "created_at":datetime.now(timezone.utc).isoformat(),
        "definition":"FBS vs FBS, current user handwritten home offense+defense unit rating positive, strictly non-neutral, AND P4 vs P4 or G6 vs G6 only, with separate group cohorts.",
        "p4":sorted(P4),
        "g6":sorted(G6),
        "exceptions":{
            "Notre Dame":"P4 all seasons",
            "Pac-12":"P4 in 2022–2023, unclassified 2024–2025, G6 in 2026",
            "unrecognized teams":"excluded; never automatically classify as G6",
        },
        "years":years,
        "combined":block(all_),
        "2026_weeks3_to6":block(recent),
        "2026_by_week":{str(w):block(recent[recent.week.eq(w)]) for w in (3,4,5,6)},
        "note":[
            "Historical model original 40/25/15/10/10 current-season internal unit ratings and prior-season/Elo blend unchanged; ONLY target matchups are filtered, as requested.",
            "Underlying pregame feature profiles still use complete earlier FBS games across opponent groups; we are not filtering earlier history.",
            "No -10 spread requirement. All point-spread and moneyline values are irrelevant for qualification.",
            "Unclassified, P4 vs G6 and G6 vs P4 are excluded from proposed same-group tier candidate.",
            "2024-2025 Pac-12 treated as unclassified for season-aware consistency; no automatic G6 assignment.",
            "2026 Weeks 3–6 and prior seasons are retrospective reconstructed earlier-week backtests, not immutable archived pregame picks.",
            "Straight-up winner accuracy is not betting profitability. Heavy favorites can inflate win rate even within group."
        ]
    }
    RESULT.parent.mkdir(parents=True,exist_ok=True)
    RESULT.write_text(json.dumps(result,indent=2,allow_nan=False,
                      default=lambda x:x.item() if isinstance(x,np.generic) else str(x))+"\n")
    # Include ALL qualifying 2026 home-both games even when cross-group;
    # this makes the newly excluded games and reasons auditable.
    eligible=recent[recent.home_both].copy().sort_values(["week","game_id"])
    eligible["result"]=np.where(eligible.home_win.eq(1),"W","L")
    cols=["week","game_id","home","away","home_conference","away_conference",
          "home_group","away_group","group_pair","same_group",
          "off_edge","def_edge","min_edge","home_points","away_points","result"]
    eligible[cols].to_csv(DETAIL,index=False)
    print(json.dumps({
        "2026_w3_to_6":result["2026_weeks3_to6"],
        "combined":result["combined"],
        "annual":{yr:{"all":v["home_both_all_pregame_eligible"],
                      "p4":v["same_group_p4_v_p4"],
                      "g6":v["same_group_g6_v_g6"],
                      "excluded":v["excluded_home_both_mixed_or_unclassified"]}
                  for yr,v in years.items()},
    },indent=2))


if __name__=="__main__":
    main()
