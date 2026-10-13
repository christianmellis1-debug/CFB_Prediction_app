"""Test D secondary check: do V1.5 changes survive the current Test C market blend?

Prerequisite: run test_d_missing_early.py to produce local candidate probabilities.
2024-25: archived ESPN BET opening lines; 2026 W5-6: genuine frozen pregame
same-book quotes from shadow_tracking.json. 2026 challenger probability deltas
are retrospective sensitivity, not recorded future forecasts.
"""
import json
from pathlib import Path
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
HIST=("https://raw.githubusercontent.com/christianmellis1-debug/"
    "CFB_Prediction_app/17a68114f48a4308d1e8312296537d701a65047b/"
    "research/test_c_historical_validation_games.csv")
WEIGHT=.16927926947215113
VARIANTS=("baseline","conservative_minus_10","conservative_minus_20",
  "half_current_weight","aggressive_plus_10","preserve_prior_when_no_snapshot",
  "conservative_minus_10_and_preserve_prior")
OUT=ROOT/"research/test_d_market_impact.json"

def score(df,v):
    p=(WEIGHT*df["p_"+v].to_numpy(float)+(1-WEIGHT)*df.market_home.to_numpy(float))
    y=df.y.to_numpy(int)
    p0=(WEIGHT*df.p_baseline.to_numpy(float)+(1-WEIGHT)*df.market_home.to_numpy(float))
    correct=(p>=.5)==y
    old=(p0>=.5)==y
    switched=(p>=.5)!=(p0>=.5)
    return dict(n=len(df),wins=int(correct.sum()),losses=int((~correct).sum()),
      accuracy=round(float(correct.mean()),6),
      brier=round(float(np.mean((p-y)**2)),6),
      changed_winners=int(switched.sum()),
      fixed=int((switched&correct).sum()),
      broken=int((switched&(~correct)).sum()))

def main():
    d=pd.read_csv(ROOT/"research/test_d_games.csv",low_memory=False)
    archived=pd.read_csv(HIST,low_memory=False)
    old=archived[archived.odds_source.eq("primary_open")][["year","id","market_home","y"]]
    full=d[d.year.isin([2024,2025])].merge(old,
      left_on=["year","game_id"],right_on=["year","id"],how="inner",suffixes=("","_market"),
      validate="one_to_one")
    assert len(full)==532
    assert (full.y==full.y_market).all()
    origin=json.loads((ROOT/"data/shadow_tracking.json").read_text())
    recent=d[(d.year.eq(2026))&d.snapshot_source.eq("frozen_baseline_delta_proxy")].copy()
    obs=[]
    for r in recent.itertuples():
        q=origin["snapshots"].get(str(r.game_id))
        assert q is not None and q["captured_at"]<q["kickoff"]
        mp=float(q["market_probability"])
        obs.append(mp if q["picked_side"]=="home" else 1-mp)
    recent["market_home"]=obs
    assert len(recent)==112
    allrows=pd.concat([full,recent],ignore_index=True)
    result={"purpose":"Do researched V1.5 alternative weights improve Test C after the locked 16.93%/83.07% market blend?",
     "limits":["Retrospective 2024/25 V1.5 and game archive opening prices, not recorded pregame predictions",
       "2026 alt model estimated as a retrospective log-odds delta to original V1.5 frozen probabilities",
       "Only Week5/6 2026 had frozen original market quotes for this matched analysis",
       "Market blend weights are not reoptimized; source books differ by period"],
     "by_year":{},"combined_2024_2025":{}}
    for year in (2024,2025,2026):
        sub=allrows[allrows.year.eq(year)]
        result["by_year"][str(year)]={v:score(sub,v) for v in VARIANTS}
    result["combined_2024_2025"]={v:score(full,v) for v in VARIANTS}
    OUT.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print("TEST_D_MARKET_OVERLAY "+json.dumps(result,sort_keys=True),flush=True)
if __name__=="__main__":
    main()
