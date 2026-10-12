"""Exact handwritten 40/25/15/10/10 offense+defense hypothesis against V1.5.

Offense: 40% adjusted EPA, 25% rush YPC, 15% pass completion rate,
10% turnovers COMMITTED (negative orientation), 10% explosive play rate.
Defense: 40% adjusted EPA allowed (negative orientation), 25% rush YPC
ALLOWED (negative), 15% pass completion rate ALLOWED (negative),
10% turnovers FORCED (positive), 10% explosive play rate ALLOWED (negative).

All six new box-stat features derive solely from complete prior-week FBS
games, with no future matchup data. Prior-season Elo/efficiency is unchanged;
the new weights apply only to the current-season contribution of V1.5.
No production or original forward-test files modified.
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit, logit

import model_v1_5 as model
from prospective_weights import component_vectors, latest
from research.run_offense_defense_2026_10_12.run import (
    prepare_schedule, metrics, valid_rush_box
)
from shadow_inputs import read_summary
from capture_value import boxes

OUT=Path("research/handwritten_offense_defense_2026_10_12/results.json")
ALPHA=model.CALIBRATION_SLOPE*1.10
WEIGHTS={"epa":.40,"run":.25,"pass":.15,"turnovers":.10,"explosive":.10}
BASE={"epa":.40,"success":.30,"explosive":.15,"red_zone":.15}
assert abs(sum(WEIGHTS.values())-1)<1e-12
assert abs(sum(BASE.values())-1)<1e-12


def prepare_full_boxes(box):
    """Unique, internally consistent team box scores only."""
    required=("game_id","team_id","rushingYards","rushingAttempts",
              "completionAttempts","turnovers","fumblesLost","interceptions")
    if not set(required).issubset(box):
        raise ValueError("Full passing/rushing/turnover box inputs missing: "+
                         ", ".join(sorted(set(required)-set(box))))
    x=box[list(required)].copy()
    for c in required:
        if c!="completionAttempts":
            x[c]=pd.to_numeric(x[c],errors="coerce")
    parsed=x.completionAttempts.astype(str).str.extract(
        r"^\s*(\d+)\s*[/−-]\s*(\d+)\s*$"
    )
    x["completions"]=pd.to_numeric(parsed[0],errors="coerce")
    x["pass_attempts"]=pd.to_numeric(parsed[1],errors="coerce")
    numeric=["game_id","team_id","rushingYards","rushingAttempts",
             "turnovers","fumblesLost","interceptions","completions",
             "pass_attempts"]
    valid=np.isfinite(x[numeric]).all(axis=1)
    valid &= x.rushingAttempts.gt(0) & x.rushingAttempts.mod(1).eq(0)
    valid &= x.pass_attempts.gt(0) & x.pass_attempts.mod(1).eq(0)
    valid &= x.completions.ge(0)&x.completions.le(x.pass_attempts)&x.completions.mod(1).eq(0)
    valid &= x[["turnovers","fumblesLost","interceptions"]].ge(0).all(axis=1)
    valid &= x[["turnovers","fumblesLost","interceptions"]].mod(1).eq(0).all(axis=1)
    valid &= x.turnovers.eq(x.fumblesLost+x.interceptions)
    valid &= x.game_id.mod(1).eq(0)&x.team_id.mod(1).eq(0)
    valid &= ~x.duplicated(["game_id","team_id"],keep=False)
    return x[valid].set_index(["game_id","team_id"],verify_integrity=True)


def standardized_team_profiles(history,lookup):
    """Return six statistically distinct prior-week box features per team.

    Teams with ANY incomplete previous FBS match fail closed. This avoids
    showing a strong run defense from only its easier, available games.
    League normalization uses available eligible FBS teams, not only the
    subsequently graded games. Totals aggregate attempts, NOT average YPC.
    """
    totals={}
    encountered=set()
    invalid=set()
    completed=0
    invalid_games=0
    for _,g in history.iterrows():
        hid,aid=int(g.home_id),int(g.away_id)
        encountered.update((hid,aid))
        keys=((g.game_id,g.home_id),(g.game_id,g.away_id))
        if not all(k in lookup.index for k in keys):
            invalid.update((hid,aid))
            invalid_games+=1
            continue
        home,away=(lookup.loc[k] for k in keys)
        for tid,own,opp in ((hid,home,away),(aid,away,home)):
            totals.setdefault(tid,np.zeros(7,dtype=float))
            # off rush yards / att; off pass completions / attempts;
            # total own giveaways (per game), total opponent rushing
            # yards / attempts, opponent pass comp / att, forced
            # takeaways (per game), number of valid team games.
            totals[tid]+=np.array([
                own.rushingYards,own.rushingAttempts,
                own.completions,own.pass_attempts,
                own.turnovers,opp.rushingYards,opp.rushingAttempts,
                opp.completions,opp.pass_attempts,opp.turnovers,1
            ]) if False else 0  # overwritten below with validated 11-length vector
        completed+=1
    # Reaggregate explicitly with 11-element vectors for clarity.
    totals={}
    for _,g in history.iterrows():
        hid,aid=int(g.home_id),int(g.away_id)
        keys=((g.game_id,g.home_id),(g.game_id,g.away_id))
        if not all(k in lookup.index for k in keys):
            continue
        h,a=(lookup.loc[k] for k in keys)
        for tid,own,opp in ((hid,h,a),(aid,a,h)):
            totals.setdefault(tid,np.zeros(11,dtype=float))
            totals[tid]+=np.array([
                own.rushingYards,own.rushingAttempts,
                own.completions,own.pass_attempts,own.turnovers,
                opp.rushingYards,opp.rushingAttempts,
                opp.completions,opp.pass_attempts,opp.turnovers,1.0
            ])
    eligible={tid:t for tid,t in totals.items()
              if tid not in invalid and t[10]>=1 and min(t[1],t[3],t[6],t[8])>0}
    quality={"completed_history_games":len(history),
             "accepted_complete_games":completed,
             "incomplete_box_games":invalid_games,
             "all_teams_seen":len(encountered),
             "teams_with_valid_full_history":len(eligible)}
    if len(eligible)<3:
        return {},quality
    ids=list(eligible)
    x=np.array([
        [t[0]/t[1],t[2]/t[3],t[4]/t[10],
         t[5]/t[6],t[7]/t[8],t[9]/t[10]]
        for t in eligible.values()
    ],dtype=float)
    means=x.mean(axis=0)
    sd=x.std(axis=0)
    if np.any(sd<=1e-10) or not np.isfinite(sd).all():
        raise ValueError("Incomplete/unvarying week-wide full-stat dispersion")
    # Off YPC+, off completion+, fewer giveaways+,
    # lower YPC allowed+, lower completions allowed+, more takeaways+.
    signs=np.array([+1,+1,-1,-1,-1,+1])
    z=(x-means)/sd*signs
    return dict(zip(ids,z)),quality


def published_required(summary, week):
    """Fail closed if a matchup team lacks the requested pregame EPA/explosive."""
    previous=summary[pd.to_numeric(summary.through_week,errors="coerce").lt(week)]
    prior=previous.sort_values("through_week").drop_duplicates("team_id",keep="last")
    out=set()
    for _,r in prior.iterrows():
        needed=[
            r.get("explosive_off"),r.get("explosive_def"),
            r.get("adj_off_epa") if pd.notna(r.get("adj_off_epa")) else r.get("EPAplay_off"),
            r.get("adj_def_epa") if pd.notna(r.get("adj_def_epa")) else r.get("EPAplay_def")
        ]
        if all(pd.notna(v) and np.isfinite(float(v)) for v in needed):
            out.add(int(r.team_id))
    return out


def year_inputs(year):
    schedule=prepare_schedule(year)
    current=read_summary(None,year)
    prior=read_summary(None,year-1)
    lookup=prepare_full_boxes(boxes(year))
    full_scores, full_weeks=component_vectors(current)
    collected=[]
    quality={}
    for week in sorted(schedule.week.dropna().astype(int).unique()):
        if week < 3 or (year==2026 and week>6):
            continue
        slate=schedule[schedule.week.eq(week)].copy()
        if slate.empty:
            continue
        first_time=slate.start.min()
        history=schedule[schedule.week.lt(week)
                         & schedule.start.lt(first_time)
                         & schedule.completed_flag
                         & schedule.home_points.notna()
                         & schedule.away_points.notna()]
        features,diagnostics=standardized_team_profiles(history,lookup)
        required=published_required(current,week)
        diagnostics["week"]=int(week)
        if not features:
            quality[str(week)]=diagnostics
            continue
        baseline=model.predict_week(current,prior,schedule,week,include_completed=True)
        probs={str(int(r["Game ID"])):float(r["Home Win %"])
               for _,r in baseline.iterrows()}
        cur_weight=model.current_season_weight(week)
        for _,g in slate.iterrows():
            if not g.completed_flag or pd.isna(g.home_points) or pd.isna(g.away_points):
                continue
            if float(g.home_points)==float(g.away_points):
                continue
            hid,aid=int(g.home_id),int(g.away_id)
            gid=str(int(g.game_id))
            if hid not in features or aid not in features or hid not in required or aid not in required or gid not in probs:
                continue
            hv,av=features[hid],features[aid]
            hc=latest(full_scores,full_weeks,hid,week)
            ac=latest(full_scores,full_weeks,aid,week)
            o=hc[0]-ac[0]
            d=hc[1]-ac[1]
            old_off=float(np.asarray([.40,.30,.15,.15])@o)
            old_def=float(np.asarray([.40,.30,.15,.15])@d)
            # Indices of independent prior-game box feature profiles:
            # 0 run off, 1 pass off, 2 fewer giveaways,
            # 3 run defense, 4 pass defense, 5 takeaways forced.
            changed_off=(.40*o[0]+.25*(hv[0]-av[0])+
                         .15*(hv[1]-av[1])+.10*(hv[2]-av[2])+.10*o[2])
            changed_def=(.40*d[0]+.25*(hv[3]-av[3])+
                         .15*(hv[4]-av[4])+.10*(hv[5]-av[5])+.10*d[2])
            delta_o=float(changed_off-old_off)
            delta_d=float(changed_def-old_def)
            p=probs[gid]
            candidate=float(expit(logit(np.clip(p,1e-12,1-1e-12))+
                 ALPHA*cur_weight*(model.OFFENSE_WEIGHT*delta_o+
                                   model.DEFENSE_WEIGHT*delta_d)))
            collected.append({
                "season":year,"week":int(week),"game_id":gid,
                "home":str(g.home_team),"away":str(g.away_team),
                "home_win":int(float(g.home_points)>float(g.away_points)),
                "baseline_probability":p,"custom_probability":candidate,
                "offense_change":delta_o,"defense_change":delta_d,
                "rush_off_edge":float(hv[0]-av[0]),
                "rush_def_edge":float(hv[3]-av[3]),
            })
        diagnostics["graded"]=sum(int(row["week"])==week for row in collected)
        quality[str(week)]=diagnostics
    if not collected:
        raise ValueError(f"No eligible complete historical games for {year}")
    return pd.DataFrame(collected),quality


def report(frame,col):
    y=frame.home_win.to_numpy(dtype=int)
    p=frame[col].to_numpy(dtype=float)
    pred=p>=.5
    success=(pred==y)
    high=np.maximum(p,1-p)>=.80
    return {
        "games":int(len(y)),"wins":int(success.sum()),
        "losses":int(len(y)-success.sum()),
        "accuracy":round(float(success.mean()),6),
        "brier":round(float(np.mean((p-y)**2)),7),
        "high_confidence_games":int(high.sum()),
        "high_confidence_wins":int(np.sum(success&high)),
        "high_confidence_accuracy":round(float(np.mean(success[high])),6) if high.any() else None,
    }


def compare(frame):
    base=frame.baseline_probability.to_numpy()>=.5
    change=frame.custom_probability.to_numpy()>=.5
    y=frame.home_win.to_numpy()==1
    changed=(base!=change)
    return {
        "changed_winners":int(changed.sum()),
        "fixed_baseline_misses":int(np.sum(changed & (change==y))),
        "introduced_new_misses":int(np.sum(changed & (base==y))),
        "examples": [
            {"week":int(x.week),"matchup":f"{x.away} at {x.home}",
             "original_pick":str(x.home if x.baseline_probability>=.5 else x.away),
             "custom_pick":str(x.home if x.custom_probability>=.5 else x.away),
             "actual":str(x.home if x.home_win else x.away)}
            for x in frame.loc[changed].itertuples(index=False)
        ][:25]
    }


def main():
    scores={}
    inputs={}
    diagnostics={}
    for year in range(2022,2027):
        frames,quality=year_inputs(year)
        inputs[str(year)]=frames
        diagnostics[str(year)]=quality
        scores[str(year)]={
            "baseline":report(frames,"baseline_probability"),
            "handwritten":report(frames,"custom_probability"),
            "changed_picks":compare(frames)
        }
        if year==2026:
            mask=frames.week.eq(6)
            if mask.any():
                scores[str(year)]["week_6"]={
                    "baseline":report(frames[mask],"baseline_probability"),
                    "handwritten":report(frames[mask],"custom_probability"),
                }
    output={
        "test":"Handwritten offense and defense 40/25/15/10/10",
        "timestamp":datetime.now(timezone.utc).isoformat(),
        "offense":{"EPA":40,"rush_YPC":25,"completion_pct":15,
                   "turnovers_committed_inverse":10,"explosive_offense":10},
        "defense":{"EPA_allowed_inverse":40,"rush_YPC_allowed_inverse":25,
                   "completion_pct_allowed_inverse":15,
                   "turnovers_forced":10,"explosive_allowed_inverse":10},
        "baseline_weights":{"offense":BASE,"defense":BASE},
        "evaluated_seasons":list(scores),
        "scores":scores,
        "coverage":diagnostics,
        "limitations":[
            "Only current-season internal component scores are changed; previous-season Elo and efficiency prior are retained unchanged.",
            "Prior-week rates are computed from complete regular-season FBS box-score game histories. Every team with incomplete past FBS game data is excluded.",
            "Each raw rushing/completion/turnover component normalized among FBS teams with fully valid histories as of the week; production EPA and explosive z-ratings used unchanged.",
            "Turnovers on offense are turnovers committed per previous game; on defense, forced takeaways per previous game. They can correlate and are not independent of offensive/defensive EPA.",
            "Completion rate is a simplistic passing-efficiency proxy. It does not account for depth of target, yards per attempt, or opponent strength.",
            "The same exact eligible games and recorded results are used for baseline and new formula. These are reconstructed, not archived pregame predictions.",
            "All five seasons have already been examined in this project; there is no pristine blind held-out test. A prospective comparison is needed before any production change.",
            "Not calibrated separately; comparing unchanged V1.5 sigmoid on the new formula tests the user's specified weights, not an optimized probability model.",
            "Measures straight-up winning and Brier only; does not establish ATS accuracy, odds-based betting value, or ROI."
        ]
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(output,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"offense":output["offense"],"defense":output["defense"],
                      "summary":scores},indent=2))


if __name__=="__main__":
    main()
