"""Historical home field tests for exact handwritten 40/25/15/10/10 units.

Both independent questions:
 A) How often do handwritten stronger offense AND stronger defense teams win
    when those advantages belong to the home team, away team, or a neutral team?
 B) Is the HOME/ROAD PERFORMANCE coefficient of 0.20 in the existing V1.5
    model helpful when the internal units are handwritten weights? Test fixed
    changes to that venue coefficient, and fixed additional home-status bonuses.

All rates and scores use the same games, with early-week pregame inputs only.
No prospective archive, live weights, app or waterfall rules are changed.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.special import expit, logit

import model_v1_5 as model
from research.handwritten_offense_defense_2026_10_12.run import (
    year_inputs, prepare_schedule
)
from research.handwritten_offense_defense_2026_10_12.confirmation_vs_v15 import (
    decisive, labels
)

OUTPUT=Path("research/handwritten_offense_defense_2026_10_12/home_field_results.json")
ALPHA=model.CALIBRATION_SLOPE*1.10
PRODUCTION_VENUE_COEFFICIENT=float(model.VENUE_WEIGHT)
VENUE_WEIGHTS=(0.0,0.10,0.20,0.30,0.40)
HOME_LOGODDS_BONUSES=(0.0,0.10,0.20,0.35)
EPS=1e-10


def venue_for_season(frame,year):
    """Regenerate EXACT production earlier-week non-neutral home/road signal."""
    schedule=prepare_schedule(year)
    lookup={str(int(r.game_id)):r for r in schedule.itertuples(index=False)}
    observations=[]
    for week,grp in frame.groupby("week",sort=True):
        home_hist,road_hist=model._completed_history(schedule,int(week))
        for r in grp.itertuples(index=False):
            g=lookup.get(str(r.game_id))
            if g is None:
                raise ValueError(f"Game {r.game_id} not found in {year} schedule")
            if int(g.week)!=int(week) or str(g.home_team)!=str(r.home) or str(g.away_team)!=str(r.away):
                raise ValueError(f"Game identity mismatch {r.game_id}")
            neutral=bool(g.neutral_site)
            h,a=int(g.home_id),int(g.away_id)
            hm=float(np.mean(home_hist[h])) if home_hist[h] else 0.
            am=float(np.mean(road_hist[a])) if road_hist[a] else 0.
            signal=((hm*len(home_hist[h])/(len(home_hist[h])+3))
                    -(am*len(road_hist[a])/(len(road_hist[a])+3)))/14.
            if neutral:
                signal=0.
            observations.append((str(r.game_id),signal,neutral))
    venue=pd.DataFrame(observations,columns=["game_id","venue_signal","neutral_site"])
    if venue.game_id.duplicated().any() or set(venue.game_id)!=set(frame.game_id):
        raise AssertionError("Unexpected venue identity coverage")
    merged=frame.merge(venue,on="game_id",how="left",validate="one_to_one",sort=False)
    if len(merged)!=len(frame) or merged[["venue_signal","neutral_site"]].isna().any().any():
        raise AssertionError("Missing corresponding venue information")
    if not np.isfinite(merged.venue_signal.to_numpy()).all():
        raise AssertionError("Nonfinite venue")
    if not np.all(merged.loc[merged.neutral_site,"venue_signal"]==0):
        raise AssertionError("Neutral site must have zero venue effect")
    return merged


def subset(mask,pred,actual):
    n=int(mask.sum())
    wins=int(np.sum(mask&(pred==actual)))
    return {"games":n,"wins":wins,"losses":n-wins,
            "win_rate":round(wins/n,6) if n else None}


def conditional_records(frame):
    o=labels(frame.proposed_offense_edge.to_numpy())
    d=labels(frame.proposed_defense_edge.to_numpy())
    neutral=frame.neutral_site.to_numpy(dtype=bool)
    y=np.where(frame.home_win.to_numpy(dtype=int)==1,1,-1)
    baseline=np.where(frame.baseline_probability.to_numpy()>=.5,1,-1)
    stronger_both=(o!=0)&(d!=0)&(o==d)
    same_both_home=stronger_both&(o==1)
    same_both_away=stronger_both&(o==-1)
    split=(o!=0)&(d!=0)&(o!=d)
    home_non_neutral=~neutral
    return {
        "all_games":len(frame),
        "non_neutral_games":int(home_non_neutral.sum()),
        "neutral_site_games":int(neutral.sum()),
        "all_non_neutral_home_team":subset(home_non_neutral,np.ones(len(frame),int),y),
        "both_advantages_home_non_neutral":subset(same_both_home&home_non_neutral,
                                               np.ones(len(frame),int),y),
        "both_advantages_away_non_neutral":subset(same_both_away&home_non_neutral,
                                               -np.ones(len(frame),int),y),
        "both_advantages_neutral":subset(stronger_both&neutral,o,y),
        "both_advantages_any_location":subset(stronger_both,o,y),
        "home_offense_edge_non_neutral":subset((o==1)&home_non_neutral,
                                             np.ones(len(frame),int),y),
        "home_defense_edge_non_neutral":subset((d==1)&home_non_neutral,
                                             np.ones(len(frame),int),y),
        "no_home_offense_or_defense_edge_non_neutral":subset(
             (o==-1)&(d==-1)&home_non_neutral,np.ones(len(frame),int),y),
        "split_advantages_non_neutral_home_team":subset(split&home_non_neutral,
                                               np.ones(len(frame),int),y),
        "split_advantages_neutral":subset(split&neutral,np.ones(len(frame),int),y),
        "v15_when_home_has_both":subset(same_both_home&home_non_neutral,baseline,y),
        "v15_when_away_has_both":subset(same_both_away&home_non_neutral,baseline,y),
        "both_home_and_v15_agree":subset(same_both_home&home_non_neutral&(baseline==1),
                                               baseline,y),
        "both_home_but_v15_picks_away":{
            "v15":subset(same_both_home&home_non_neutral&(baseline==-1),baseline,y),
            "handwritten_home":subset(same_both_home&home_non_neutral&(baseline==-1),
                                      np.ones(len(frame),int),y)},
        "both_away_but_v15_picks_home":{
            "v15":subset(same_both_away&home_non_neutral&(baseline==1),baseline,y),
            "handwritten_away":subset(same_both_away&home_non_neutral&(baseline==1),
                                      -np.ones(len(frame),int),y)},
    }


def grade_probability(frame,prob):
    y=frame.home_win.to_numpy(dtype=int)
    p=np.clip(np.asarray(prob,dtype=float),1e-12,1-1e-12)
    n=len(y)
    wins=int(((p>=.5)==y).sum())
    return {"games":n,"wins":wins,"losses":n-wins,
            "accuracy":round(wins/n,6) if n else None,
            "brier":round(float(np.mean((p-y)**2)),7) if n else None,
            "log_loss":round(float(np.mean(-y*np.log(p)-(1-y)*np.log1p(-p))),7) if n else None}


def new_probability(frame,venue_weight=None,home_bonus=0.0):
    """Only modify venue log-odds relative to handwritten production baseline."""
    if venue_weight is None:
        venue_weight=PRODUCTION_VENUE_COEFFICIENT
    base=frame.custom_probability.to_numpy(dtype=float)
    v=frame.venue_signal.to_numpy(dtype=float)
    neutral=frame.neutral_site.to_numpy(dtype=bool)
    return expit(logit(np.clip(base,1e-12,1-1e-12))
         +ALPHA*(venue_weight-PRODUCTION_VENUE_COEFFICIENT)*v
         +float(home_bonus)*(~neutral))


def probability_tests(frame):
    results={
       "existing_v15":grade_probability(frame,frame.baseline_probability.to_numpy()),
       "handwritten_existing_venue":grade_probability(frame,frame.custom_probability.to_numpy()),
    }
    for weight in VENUE_WEIGHTS:
        p=new_probability(frame,venue_weight=weight)
        results[f"venue_coefficient_{int(weight*100):02d}pct"]={
          "all":grade_probability(frame,p),
          "non_neutral":grade_probability(frame.loc[~frame.neutral_site],p[~frame.neutral_site.to_numpy()]),
          "neutral":grade_probability(frame.loc[frame.neutral_site],p[frame.neutral_site.to_numpy()]),
        }
    for bonus in HOME_LOGODDS_BONUSES[1:]:
        p=new_probability(frame,home_bonus=bonus)
        results[f"extra_home_logodds_{bonus:.2f}"]={
          "all":grade_probability(frame,p),
          "non_neutral":grade_probability(frame.loc[~frame.neutral_site],p[~frame.neutral_site.to_numpy()]),
          "neutral":grade_probability(frame.loc[frame.neutral_site],p[frame.neutral_site.to_numpy()]),
        }
    return results


def main():
    frames={}
    report={}
    for year in range(2022,2027):
        data,quality=year_inputs(year)
        merged=venue_for_season(data,year)
        frames[str(year)]=merged
        report[str(year)]={
            "conditions":conditional_records(merged),
            "model_tests":probability_tests(merged),
        }
    all_frame=pd.concat(frames.values(),ignore_index=True)
    total=conditional_records(all_frame)
    scores=probability_tests(all_frame)
    baseline=scores["handwritten_existing_venue"]
    ranked=[
        {"name":name,"2024":report["2024"]["model_tests"][name]["all"],
         "2025":report["2025"]["model_tests"][name]["all"],
         "2026":report["2026"]["model_tests"][name]["all"],
         "combined":score["all"]}
        for name,score in scores.items()
        if isinstance(score,dict) and "all" in score
    ]
    result={
        "date":datetime.now(timezone.utc).isoformat(),
        "status":"retrospective research only, no change to production",
        "hypothesis":"User's handwritten 40/25/15/10/10 offense and defense ratings plus independent home field assessment",
        "existing_venue_weight":PRODUCTION_VENUE_COEFFICIENT,
        "method":"Same 2826 earlier-week eligible FBS games as original handwritten model audit. Reconstruct exact production venue signal on the same season/week; compare descriptive home/away/neutral cases, then change only venue coefficient or fixed extra home bonus in LOG ODDS of handwritten model.",
        "by_year":report,
        "combined":{
            "conditions":total,
            "model_tests":scores,
            "candidate_ranked_by_2024_brier":sorted(ranked,key=lambda x:x["2024"]["brier"]),
        },
        "limitations":[
            "Current V1.5 and handwritten model already include a 20% historical home/road performance component; this test is the effect of modifying that coefficient, not adding previously absent home advantage.",
            "Varying venue coefficients without renormalizing offense/defense/SOS is intentional to isolate the effect. The coefficients need not sum to 1 in these research variants.",
            "A constant extra home log-odds boost tests a separate home-status hypothesis; it is not equivalent to giving the production historical home/road statistic more weight.",
            "Neutral-site games receive no home-field adjustment; home and away assignments at neutral venues are not treated as home advantage.",
            "All figures are retrospective simulations, not prospective frozen actual predictions; data may have been revised since games.",
            "These historical seasons were already examined; a selected model is likely optimistic. Future locked forward tests are essential before production changes.",
            "Straight-up win rates, Brier and log loss only; no ATS or market price ROI conclusions.",
            "Conditional win rates reflect team strength and opponent quality as well as home venue; they do not independently prove a causal home-field advantage."
        ],
    }
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(result,indent=2,allow_nan=False,default=lambda x:x.item() if isinstance(x,np.generic) else str(x))+"\n")
    print(json.dumps({
      "by_year_conditions":{year:x["conditions"] for year,x in report.items()},
      "combined_conditions":total,
      "baseline_handwritten":baseline,
      "candidate_ranked_by_2024_brier":result["combined"]["candidate_ranked_by_2024_brier"],
    },indent=2))


if __name__=="__main__":
    main()
