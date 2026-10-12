"""How often does the higher-rated offense/defense win under handwritten weights?

Strict head-to-head comparisons on identical earlier-week historical records.
Primary rating is the *blended* team rating used by V1.5: current-season
handwritten 40/25/15/10/10 + unchanged prior-season rating/Elo.
For context, compare the original V1.5 offense/defense ratings on those SAME
games. A "both" match has ONE team with a strictly higher offense AND defense.
A "split" match has different teams ahead on offense and defense.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import numpy as np
import pandas as pd

from research.handwritten_offense_defense_2026_10_12.run import year_inputs

OUT=Path("research/handwritten_offense_defense_2026_10_12/unit_advantage_results.json")
EPS=1e-10


def summarize(frame, offensive="proposed_offense_edge", defensive="proposed_defense_edge"):
    if frame.empty:
        raise ValueError("No eligible matchup data")
    o=frame[offensive].to_numpy(dtype=float)
    d=frame[defensive].to_numpy(dtype=float)
    winner=frame.home_win.to_numpy(dtype=int)
    if not (np.isfinite(o).all() and np.isfinite(d).all()
            and np.isin(winner,[0,1]).all()):
        raise ValueError("Missing or invalid team ratings/outcomes")
    os=np.where(o>EPS,1,np.where(o< -EPS,-1,0))
    ds=np.where(d>EPS,1,np.where(d< -EPS,-1,0))
    actual_side=np.where(winner==1,1,-1)
    has_o=os!=0
    has_d=ds!=0
    both=has_o & has_d & (os==ds)
    split=has_o & has_d & (os==-ds)
    one_tie=has_o ^ has_d
    both_tie=~has_o & ~has_d
    assert np.all(both|split|one_tie|both_tie)
    assert int(np.sum(both|split|one_tie|both_tie))==len(frame)
    def win(mask, side):
        n=int(np.sum(mask))
        wins=int(np.sum(mask & (side==actual_side)))
        return {"games":n,"wins":wins,"losses":n-wins,
                "win_rate":round(wins/n,6) if n else None}
    result={
        "total_games":len(frame),
        "higher_offense":win(has_o,os),
        "higher_defense":win(has_d,ds),
        "same_team_better_at_both":win(both,os),
        "different_teams_split_the_edges":{
            "games":int(np.sum(split)),
            "better_offense":win(split,os),
            "better_defense":win(split,ds)
        },
        "one_metric_tied_games":int(np.sum(one_tie)),
        "both_metrics_tied_games":int(np.sum(both_tie)),
        "mean_abs_offense_rating_diff":round(float(np.mean(np.abs(o))),4),
        "mean_abs_defense_rating_diff":round(float(np.mean(np.abs(d))),4)
    }
    assert result["same_team_better_at_both"]["games"]+result["different_teams_split_the_edges"]["games"]+result["one_metric_tied_games"]+result["both_metrics_tied_games"]==len(frame)
    return result


def main():
    all_frames=[]
    years={}
    diagnostics={}
    for year in range(2022,2027):
        frame,quality=year_inputs(year)
        if not all(x in frame for x in (
            "original_offense_edge","original_defense_edge",
            "proposed_offense_edge","proposed_defense_edge")):
            raise AssertionError("Missing original/proposed rating edges")
        # The revised internal score has to match the previous A/B-test
        # delta for each game, proving the offense/defense comparisons are
        # based on precisely the same proposed probabilities as before.
        w=frame.current_weight.to_numpy()
        off=np.asarray(frame.proposed_offense_edge-frame.original_offense_edge)
        de=np.asarray(frame.proposed_defense_edge-frame.original_defense_edge)
        eoff=np.asarray(frame.offense_change*w)
        edef=np.asarray(frame.defense_change*w)
        error=max(float(np.max(np.abs(off-eoff))),float(np.max(np.abs(de-edef))))
        if error>1e-10:
            raise AssertionError(f"{year}: blended unit scores are inconsistent {error}")
        years[str(year)]={
            "proposed":summarize(frame),
            "existing_v15":summarize(frame,
                                   "original_offense_edge","original_defense_edge")
        }
        diagnostics[str(year)]={"max_edge_parity_error":error,
                                "eligible_games":len(frame),
                                "excluded_earlier_box_data":quality}
        all_frames.append(frame)
    total=pd.concat(all_frames,ignore_index=True)
    output={
        "created_at":datetime.now(timezone.utc).isoformat(),
        "interpretation":"Best means the higher-rated team IN THAT MATCHUP, not nationally the top-ranked offense/defense.",
        "model":"User handwritten 40% EPA, 25% rushing YPC, 15% passing completion %, 10% turnovers, 10% explosive plays in both offense and defense; original production preseason ratings maintained.",
        "definition":"Head-to-head strictly greater offense or defense score from exact V1.5 blended team ratings with handwritten current-season internal coefficients. Both = same team ahead at offense and defense; split = opposite teams ahead. Exact ties separated.",
        "by_season":years,
        "combined":{
            "proposed":summarize(total),
            "existing_v15":summarize(total,
                                   "original_offense_edge","original_defense_edge")
        },
        "parity":diagnostics,
        "limitations":[
            "2022-2025 through regular season, 2026 only completed Weeks 3-6; all are retrospective, not originally locked pregame.",
            "Only Week 3+ completed regular-season FBS games with complete earlier-week rushing/passing/turnovers and EPA/explosive stats; not a complete schedule.",
            "Current-season ratings use the exact handwritten proposal; prior-season efficiency/Elo ratings stay unchanged as in the previous A/B test.",
            "Higher offensive or defensive pregame rating is an association and not a controlled causal test. Better teams can also have more talent, easier schedules, home-field advantages, or favorable betting lines.",
            "Two-team results on a single game: when offense and defense split, the offense advantage record and defense advantage record must sum to all split games.",
            "All 2022-2026 seasons have been examined elsewhere; none is a truly unseen prospective holdout.",
            "This is straight-up winner rate only. A 70% win rate does not establish ATS/ML betting profitability.",
            "No production formula, official Value Shortlist, or existing immutable prospectively captured picks are changed."
        ]
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(output,indent=2,allow_nan=False)+"\n")
    print(json.dumps({
        "by_season":{year:v["proposed"] for year,v in years.items()},
        "combined":output["combined"],
        "edge_parity":{year:v["max_edge_parity_error"] for year,v in diagnostics.items()}
    },indent=2))


if __name__=="__main__":
    main()
