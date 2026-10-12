"""Run-offense / run-defense V1.5 redesign sensitivity, without production edits.

Does EPA or success rate deserve a place next to independent rushing ability?
Rushing offense and rushing defense use team-season YPC from *earlier-week*
completed FBS games only, with valid matched two-sided box scores. They are
standardized across all observed FBS teams as of each pregame week, and added
as independent internal offense/defense components. Other main-model terms,
the prior-year Elo/efficiency mix and the probability sigmoid stay unchanged.

2022-23 development, 2024 selection, 2025/2026 descriptive validation.
All seasons have been examined before; prospective testing is necessary.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import math

import numpy as np
import pandas as pd
from scipy.special import expit, logit

import model_v1_5 as model
from shadow_inputs import download_schedule, read_summary
from capture_value import boxes
from matchup_advantages import normalize_fbs_schedule
from prospective_weights import component_vectors, latest, prior_excluded_ids

OUT = Path("research/run_offense_defense_2026_10_12/results.json")
FEATURES = ("epa", "success", "explosive", "red_zone", "rush")
BASE = np.array([.40, .30, .15, .15, .00], dtype=float)
ALPHA = model.CALIBRATION_SLOPE * 1.10

# Each non-baseline candidate intentionally omits ONE of EPA / success rate:
# we investigate redundancy, not assume that dropping either is necessarily wise.
FORMULAS = {
    "current_no_rush": (.40, .30, .15, .15, .00),
    "epa_rush_20": (.45, .00, .20, .15, .20),
    "epa_rush_35": (.35, .00, .15, .15, .35),
    "epa_rush_50": (.30, .00, .10, .10, .50),
    "success_rush_20": (.00, .45, .20, .15, .20),
    "success_rush_35": (.00, .35, .15, .15, .35),
    "success_rush_50": (.00, .30, .10, .10, .50),
    "both_rush_25": (.30, .25, .10, .10, .25),  # control: retain both
}
assert all(np.isclose(sum(w),1) and min(w)>=0 for w in FORMULAS.values())

PLANS = [("baseline", "current_no_rush", "current_no_rush")]
for key in list(FORMULAS)[1:]:
    PLANS.extend([(f"offense_{key}",key,"current_no_rush"),
                  (f"defense_{key}","current_no_rush",key),
                  (f"both_{key}",key,key)])
for o,d in [
    ("epa_rush_20","epa_rush_35"),
    ("epa_rush_35","epa_rush_20"),
    ("epa_rush_35","epa_rush_50"),
    ("epa_rush_50","epa_rush_35"),
    ("epa_rush_35","success_rush_35"),
    ("success_rush_35","epa_rush_35"),
    ("success_rush_35","success_rush_50"),
    ("epa_rush_50","success_rush_50"),
    ("success_rush_50","epa_rush_50"),
    ("epa_rush_20","success_rush_35"),
    ("success_rush_20","epa_rush_35"),
]:
    PLANS.append((f"off_{o}_def_{d}",o,d))
assert len(PLANS)==len(set(p[0] for p in PLANS))


def prepare_schedule(year):
    s=download_schedule(year)
    s=s[s.season_type.astype(str).str.lower().eq("regular")].copy()
    s=normalize_fbs_schedule(s)
    for col in ("season","week","game_id","home_id","away_id","home_points","away_points"):
        s[col]=pd.to_numeric(s[col],errors="coerce")
    s=s.dropna(subset=["week","game_id","home_id","away_id"])
    s["start"]=pd.to_datetime(s.start_date,errors="coerce",utc=True)
    s["completed_flag"]=s.completed.astype(str).str.lower().isin(
        ("true","t","1","1.0","yes","y"))
    return s


def valid_rush_box(box):
    """Do not include ambiguous, invalid, or partial teammate box scores."""
    cols=["game_id","team_id","rushingYards","rushingAttempts"]
    if not set(cols).issubset(box):
        raise ValueError("FBS rushing box columns missing")
    x=box[cols].copy()
    for c in cols:
        x[c]=pd.to_numeric(x[c],errors="coerce")
    valid=np.isfinite(x[cols]).all(axis=1)
    valid &= x.rushingAttempts.gt(0) & x.rushingAttempts.mod(1).eq(0)
    valid &= x.game_id.mod(1).eq(0) & x.team_id.mod(1).eq(0)
    valid &= ~x.duplicated(["game_id","team_id"],keep=False)
    return x[valid].set_index(["game_id","team_id"],verify_integrity=True)


def rush_zscores(history, lookup):
    """League-wide pregame z-ratings, one row per team, offense and defense.

    Every included game requires a usable matched box-score pair. Opposing
    offense YPC becomes own run-defense YPC allowed. Incomplete games do not
    contribute to either team, so there is no one-sided selection bias.
    """
    totals={}
    accepted=0
    missing=0
    for _,g in history.iterrows():
        keys=((g.game_id,g.home_id),(g.game_id,g.away_id))
        if not all(key in lookup.index for key in keys):
            missing+=1
            continue
        h,a=(lookup.loc[key] for key in keys)
        if any(not np.isfinite(x) for x in (
            h.rushingYards,h.rushingAttempts,a.rushingYards,a.rushingAttempts
        )):
            missing+=1
            continue
        for own,opp,tid in ((h,a,int(g.home_id)),(a,h,int(g.away_id))):
            totals.setdefault(tid,np.zeros(4,dtype=float))
            totals[tid] += np.array([
                own.rushingYards,own.rushingAttempts,
                opp.rushingYards,opp.rushingAttempts
            ])
        accepted+=1

    if len(totals)<2:
        return {}, {"complete_past_games":accepted, "missing_box_games":missing,
                    "teams":len(totals)}
    ids=list(totals)
    raw=np.array([[
        totals[t][0]/totals[t][1],
        totals[t][2]/totals[t][3]
    ] for t in ids])
    if not np.all(np.isfinite(raw)):
        raise ValueError("Unusable aggregate rushing rates")
    mean=raw.mean(axis=0)
    sd=raw.std(axis=0)
    if np.any(sd<=1e-10):
        return {}, {"complete_past_games":accepted, "missing_box_games":missing,
                    "teams":len(totals), "reason":"No rushing variance"}
    z=(raw-mean)/sd
    # Lower rush YPC allowed = higher defensive rating.
    z[:,1] = -z[:,1]
    return dict(zip(ids,map(tuple,z))), {
        "complete_past_games":accepted,
        "missing_box_games":missing,
        "teams":len(totals),
        "run_offense_mean":float(mean[0]),
        "run_offense_sd":float(sd[0]),
        "run_defense_allowed_mean":float(mean[1]),
        "run_defense_allowed_sd":float(sd[1])
    }


def variants_for_week(current,prior,schedule,lookup,week):
    """All games share a strictly earlier-week league-wide rush z scale."""
    week_games=schedule[schedule.week.eq(week)].copy()
    if week_games.empty:
        return [],{}
    first_kickoff=week_games.start.min()
    if pd.isna(first_kickoff):
        return [],{}
    history=schedule[
        schedule.week.lt(week) & schedule.start.lt(first_kickoff)
        & schedule.completed_flag
        & schedule.home_points.notna() & schedule.away_points.notna()
    ]
    rush,quality=rush_zscores(history,lookup)
    quality["week"]=week
    if not rush:
        return [],quality
    scores,weeks=component_vectors(current)
    # Baseline exact production model probabilities.
    predictions=model.predict_week(current,prior,schedule,week,include_completed=True)
    by_id={str(int(r["Game ID"])):float(r["Home Win %"])
           for _,r in predictions.iterrows()}

    rows=[]
    season_weight=model.current_season_weight(week)
    for _,g in week_games.iterrows():
        if not g.completed_flag or pd.isna(g.home_points) or pd.isna(g.away_points):
            continue
        if float(g.home_points)==float(g.away_points):
            continue
        gid=str(int(g.game_id))
        home,away=int(g.home_id),int(g.away_id)
        if gid not in by_id or home not in rush or away not in rush:
            continue
        hc,ac=latest(scores,weeks,home,week),latest(scores,weeks,away,week)
        odiff=hc[0]-ac[0]
        ddiff=hc[1]-ac[1]
        # Production current ratings are replicated from 4 standardized inputs.
        base_off=float(BASE[:4]@odiff)
        base_def=float(BASE[:4]@ddiff)
        adjusted_off=np.r_[odiff,rush[home][0]-rush[away][0]]
        adjusted_def=np.r_[ddiff,rush[home][1]-rush[away][1]]
        if abs(float(BASE@adjusted_off)-base_off)>1e-10 or abs(float(BASE@adjusted_def)-base_def)>1e-10:
            raise AssertionError("Baseline component parity lost")
        row={
            "year":int(g.season),"week":week,"game_id":gid,
            "home":str(g.home_team),"away":str(g.away_team),
            "home_win":int(float(g.home_points)>float(g.away_points)),
            "base_p":by_id[gid],
            "current_weight":season_weight,
        }
        # Change CURRENT-season offensive or defensive internal ratings only.
        # Preserve the prior-season/Elo prior and all other V1.5 terms.
        for key,w in FORMULAS.items():
            delta_o=float((np.array(w)-BASE)@adjusted_off)
            delta_d=float((np.array(w)-BASE)@adjusted_def)
            row["o_"+key]=delta_o
            row["d_"+key]=delta_d
        rows.append(row)
    quality["graded"]=len(rows)
    return rows,quality


def build_year(year):
    s=prepare_schedule(year)
    box=boxes(year)
    lookup=valid_rush_box(box)
    current=read_summary(None,year)
    previous=read_summary(None,year-1)
    out=[]
    diagnostics={}
    for week in sorted(s.week.dropna().astype(int).unique()):
        if week<3:
            continue
        if year==2026 and week>6:
            break
        rows,quality=variants_for_week(current,previous,s,lookup,week)
        diagnostics[str(week)]=quality
        out.extend(rows)
    if not out:
        raise ValueError(f"Missing full-rushing pregame cohort in {year}")
    return pd.DataFrame(out),diagnostics


def probabilities(frame, offense, defense):
    baseline=np.clip(frame.base_p.to_numpy(dtype=float),1e-12,1-1e-12)
    season=frame.current_weight.to_numpy(dtype=float)
    delta=(model.OFFENSE_WEIGHT*frame["o_"+offense].to_numpy()
           +model.DEFENSE_WEIGHT*frame["d_"+defense].to_numpy())
    return expit(logit(baseline)+ALPHA*season*delta)


def metrics(frame,p):
    y=frame.home_win.to_numpy(dtype=int)
    right=((p>=.5)==y)
    confidence=np.maximum(p,1-p)
    hi=confidence>=.8
    return {
        "games":len(y),"wins":int(right.sum()),
        "accuracy":round(float(right.mean()),6),
        "brier":round(float(np.mean((p-y)**2)),7),
        "log_loss":round(float(np.mean(
            -(y*np.log(np.clip(p,1e-12,1-1e-12))
              +(1-y)*np.log(np.clip(1-p,1e-12,1-1e-12))))),7),
        "high_confidence_games":int(hi.sum()),
        "high_confidence_wins":int(np.sum(right&hi)),
        "high_confidence_accuracy":round(float(np.mean(right[hi])),6) if hi.any() else None,
    }


def main():
    frames={}
    coverage={}
    for year in (2022,2023,2024,2025,2026):
        frame,quality=build_year(year)
        frames[str(year)]=frame
        coverage[str(year)]=quality
    all_results=[]
    for name,o,d in PLANS:
        season_scores={}
        for year,frame in frames.items():
            p=probabilities(frame,o,d)
            values={"all":metrics(frame,p)}
            if year=="2026":
                wk=frame.week.eq(6)
                if wk.any():
                    values["week_6"]=metrics(frame[wk],p[wk.to_numpy()])
            season_scores[year]=values
        all_results.append({
            "name":name,"offense":dict(zip(FEATURES,FORMULAS[o])),
            "defense":dict(zip(FEATURES,FORMULAS[d])),
            "scores":season_scores
        })
    baseline=all_results[0]
    for year,frame in frames.items():
        verify=probabilities(frame,"current_no_rush","current_no_rush")
        if np.max(np.abs(verify-frame.base_p.to_numpy()))>1e-12:
            raise AssertionError("Original V1.5 probabilities not reproduced")
    initial=baseline["scores"]["2024"]["all"]
    candidates=[r for r in all_results[1:] if
        r["scores"]["2024"]["all"]["brier"]<initial["brier"]
        and r["scores"]["2024"]["all"]["accuracy"]>=initial["accuracy"]-.01]
    chosen=min(candidates,key=lambda x:x["scores"]["2024"]["all"]["brier"]) if candidates else None
    output={
        "created_at":datetime.now(timezone.utc).isoformat(),
        "status":"retrospective research only: no production weights or tier changes",
        "design":"Independent rushing offense/run defense standardized across all teams with valid earlier-week FBS games. Other input components are production-standardized. Prior blend retained unchanged. Zero out EITHER EPA or success rate in test families.",
        "years":{y:len(f) for y,f in frames.items()},
        "coverage":coverage,
        "baseline":baseline,
        "selected_by_2024_brier":chosen,
        "all_results":all_results,
        "limitations":[
            "Sportsdataverse historical inputs may have changed since pregame. These are retrospective simulations.",
            "Incomplete matched two-sided rushing box scores exclude affected games; cohort identical across all tested formulas.",
            "Same-season FBS vs FBS completed games, Week 3 onward only; rushing data for 2026 ends Week 6.",
            "2025/2026 have been examined previously and are not fully untouched unseen holdout seasons.",
            "Multiple prespecified candidate variants still create selection risk; prospective lock-before-kickoff testing is necessary.",
            "Only CURRENT-season offensive and defensive within-unit formula changes; prior-season efficiency/Elo blend, venue, SOS and conference log-odds fixed.",
            "Run offense measured with rushing yards / rushing attempts; run defense uses opponent YPC allowed. These are not opponent-adjusted, so schedule/competition confounding must be checked.",
            "EPA and success rate can share signal, but whether removing one improves out-of-season forecasting must be tested. No assumption of redundancy proves they are interchangeable.",
            "These are straight-up winners and probability scores, not ATS bets, market edges, or betting ROI."
        ]
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(output,indent=2,allow_nan=False)+"\n")
    def display(row):
        return {
            "name":row["name"],
            "offense":row["offense"],
            "defense":row["defense"],
            "scores":{y:v["all"] for y,v in row["scores"].items()},
            "week6":row["scores"]["2026"].get("week_6")
        }
    print(json.dumps({
        "cohorts":output["years"],
        "baseline":display(baseline),
        "selected":display(chosen) if chosen else None,
        "top_2024":[display(x) for x in sorted(
            all_results,key=lambda x:x["scores"]["2024"]["all"]["brier"])[:8]],
        "top_2025":[display(x) for x in sorted(
            all_results,key=lambda x:x["scores"]["2025"]["all"]["brier"])[:8]],
        "top_2026":[display(x) for x in sorted(
            all_results,key=lambda x:x["scores"]["2026"]["all"]["brier"])[:8]],
    },indent=2))


if __name__=="__main__":
    main()
