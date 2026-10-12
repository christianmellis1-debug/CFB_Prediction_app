"""Paired confirmation test: handwritten BOTH-unit advantage versus V1.5.

Among the SAME eligible completed games, ask whether the winner when both
proposed unit advantages align provides extra information over production
V1.5. Freeze two deterministic hypothetical decisions:
  baseline: V1.5 home_win_probability >= 0.50
  confirm_flip: use the BOTH advantage if available; otherwise V1.5.
Also compare veto-only (abstain when V1.5 conflicts with BOTH), and contrast
the original V1.5-unit confirmation as a fair benchmark.

This is retrospective and makes no changes to production picks/odds.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

from research.handwritten_offense_defense_2026_10_12.run import year_inputs

OUT=Path("research/handwritten_offense_defense_2026_10_12/confirmation_vs_v15_results.json")
EPS=1e-10


def labels(x):
    a=np.asarray(x,dtype=float)
    if not np.isfinite(a).all():
        raise ValueError("Invalid source rating or probability")
    return np.where(a>EPS,1,np.where(a< -EPS,-1,0))


def decisive(mask, predicted, actual):
    n=int(np.sum(mask))
    wins=int(np.sum(mask & (predicted==actual)))
    return {"games":n,"wins":wins,"losses":n-wins,
            "accuracy":round(wins/n,6) if n else None}


def analyze(frame, use_proposed=True):
    if not len(frame):
        raise ValueError("Empty cohort")
    off="proposed_offense_edge" if use_proposed else "original_offense_edge"
    defense="proposed_defense_edge" if use_proposed else "original_defense_edge"
    o=labels(frame[off].to_numpy())
    d=labels(frame[defense].to_numpy())
    y=np.where(frame.home_win.to_numpy(dtype=int)==1,1,-1)
    p=frame.baseline_probability.to_numpy(dtype=float)
    if np.any(~np.isfinite(p)) or np.any((p<=0)|(p>=1)):
        raise ValueError("Invalid baseline probabilities")
    v15=np.where(p>=.5,1,-1)
    both=(o!=0)&(d!=0)&(o==d)
    split=(o!=0)&(d!=0)&(o!=d)
    partial=(o==0)^(d==0)
    double_tie=(o==0)&(d==0)
    assert int((both|split|partial|double_tie).sum())==len(frame)
    agree=both & (o==v15)
    disagree=both & (o!=v15)
    confidence=np.maximum(p,1-p)
    # deterministic, post hoc test policies; can be prospective candidates later
    flip=np.where(both,o,v15)
    confirm_available=agree
    report={
      "cohort_games":len(frame),
      "baseline_all":decisive(np.ones(len(frame),bool),v15,y),
      "rule_flip_all":decisive(np.ones(len(frame),bool),flip,y),
      "new_wins_over_baseline":int(((flip==y)&(v15!=y)).sum()),
      "new_losses_over_baseline":int(((flip!=y)&(v15==y)).sum()),
      "net_winners_changed":int((flip==y).sum()-(v15==y).sum()),
      "both_available":decisive(both,o,y),
      "both_v15_agree":decisive(agree,v15,y),
      "both_v15_disagree":{
         "v15":decisive(disagree,v15,y),
         "handwritten_both":decisive(disagree,o,y),
      },
      "split_available":{
         "baseline":decisive(split,v15,y),
         "higher_offense":decisive(split,o,y),
         "higher_defense":decisive(split,d,y),
      },
      "v15_abstain_if_both_disagrees":{
         "bettable_games":int((~disagree).sum()),
         "avoided_games":int(disagree.sum()),
         "retained_v15":decisive(~disagree,v15,y),
         "avoided_v15":decisive(disagree,v15,y),
         "avoided_handwritten":decisive(disagree,o,y)
      },
      "v15_picks_confirmed_only":decisive(confirm_available,v15,y),
      "no_both_advantage_games":int((~both).sum()),
      "ties_or_missing_edge_games":int((partial|double_tie).sum()),
      "by_baseline_confidence":{
         label:{
             "both_conflicts_v15": {
                 "v15":decisive(disagree&mask,v15,y),
                 "handwritten_both":decisive(disagree&mask,o,y)
             },
             "all_games_v15":decisive(mask,v15,y),
         }
         for label,mask in [
             ("50_to_59pct",confidence<.60),
             ("60_to_69pct",(confidence>=.60)&(confidence<.70)),
             ("70_to_79pct",(confidence>=.70)&(confidence<.80)),
             ("80pct_plus",confidence>=.80),
         ]
      }
    }
    for name,row in [
        ("agree",report["both_v15_agree"]),
        ("disagree",report["both_v15_disagree"]["v15"]),
    ]:
        if row["games"]<0:
            raise AssertionError(name)
    if report["both_v15_agree"]["games"]+report["both_v15_disagree"]["v15"]["games"]!=report["both_available"]["games"]:
        raise AssertionError("Incorrect confirmation partition")
    if report["new_wins_over_baseline"] != report["both_v15_disagree"]["handwritten_both"]["wins"]:
        raise AssertionError("New wins must come only from resolved conflicts")
    if report["new_losses_over_baseline"] != report["both_v15_disagree"]["v15"]["wins"]:
        raise AssertionError("New losses must come only from resolved conflicts")
    return report


def conflict_examples(frame,limit=16):
    off=labels(frame.proposed_offense_edge.to_numpy())
    defense=labels(frame.proposed_defense_edge.to_numpy())
    both=(off!=0)&(defense!=0)&(off==defense)
    p=frame.baseline_probability.to_numpy(dtype=float)
    original=np.where(p>=.5,1,-1)
    mask=both & (off!=original)
    disagreed=frame.loc[mask].copy()
    disagreed["abs_confidence"]=np.maximum(disagreed.baseline_probability,1-disagreed.baseline_probability)
    disagreed=disagreed.sort_values("abs_confidence",ascending=False)
    rows=[]
    for r in disagreed.head(limit).itertuples(index=False):
        home=int(r.home_win)==1
        v15_home=r.baseline_probability>=.5
        both_home=float(r.proposed_offense_edge)>0
        rows.append({
            "season":int(r.season),"week":int(r.week),
            "game":f"{r.away} at {r.home}",
            "v15_pick":str(r.home if v15_home else r.away),
            "v15_confidence":round(max(float(r.baseline_probability),1-float(r.baseline_probability)),3),
            "both_advantage_pick":str(r.home if both_home else r.away),
            "actual_winner":str(r.home if home else r.away),
            "v15_won":bool(v15_home==home),
            "handwritten_won":bool(both_home==home)
        })
    return rows


def main():
    years={}
    frames=[]
    for year in range(2022,2027):
        frame,quality=year_inputs(year)
        years[str(year)]={
            "proposed":analyze(frame),
            "original_units":analyze(frame,use_proposed=False),
            "v15_conflicting_examples":conflict_examples(frame,limit=20),
        }
        frames.append(frame)
    combined=pd.concat(frames,ignore_index=True)
    output={
        "test":"Does the exact handwritten both-advantage signal improve original V1.5 on identical games?",
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "years":years,
        "combined":{
            "proposed":analyze(combined),
            "original_units":analyze(combined,use_proposed=False),
            "v15_conflicting_examples":conflict_examples(combined,limit=25),
        },
        "sample_sizes":{str(year):len(f) for year,f in zip(range(2022,2027),frames)},
        "important_notes":[
            "The rule always keeps V1.5 when handwritten unit advantages split; it flips ONLY when handwritten offense AND defense favor the SAME other team.",
            "The rule is a hypothetical retrospective deterministic experiment, not a current production or value-tier selection.",
            "Confirmation-filter accuracy and full-schedule accuracy differ in coverage. A high confirmed subset accuracy cannot automatically be compared to overall V1.5 accuracy.",
            "All reported disagreements compare identical pregame stat availability; games were chosen by statistics and not by their final outcome.",
            "A veto that abstains on disagreement can boost conditional hit rate by avoiding bets, but reduced coverage and the omitted results must be disclosed.",
            "The original V1.5 offense/defense unit agreement is tested as a comparator using the SAME identical games, not a different qualifying population.",
            "Historical data 2022-2026 are retrospective, have been examined previously, and could contain revisions; prospectively locked validation is required.",
            "No ATS, moneyline, payout/ROI inference. Wins are straight-up winners only. Conference/home/SOS effects remain in V1.5 baseline."
        ],
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(output,indent=2,allow_nan=False,default=lambda x:x.item() if isinstance(x,np.generic) else str(x))+"\n")
    print(json.dumps({
        "sample_sizes":output["sample_sizes"],
        "combined":output["combined"],
        "per_year":{year:info["proposed"] for year,info in years.items()},
    },indent=2))


if __name__=="__main__":
    main()
