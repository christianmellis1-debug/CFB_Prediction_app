"""Follow-up: pre-selected Test E family rules applied together, no refitting.

Reads existing exact archived game-level predictions created by the completed
six-family Test E experiment. Combination chosen independently of the 2025
and 2026 results: add market-weight changes, add football-component log-odds
deltas; cap total V1.5 weight to the range [0.05,0.65].
No production modifications.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import logit,expit

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"research/test_e_six_signals_games.csv"
OUT=ROOT/"research/test_e_combination_results.json"
W=.16927926947215113

def combine(d,names):
    w=np.full(len(d),W,dtype=float)
    market=d.market.to_numpy(float)
    old=d.v15.to_numpy(float)
    for short,column,weight in [
        ("E1","E1_close_games",.10),("E2","E2_disagreement",.35),
        ("E6","E6_stat_reliability",.35)]:
        if short in names:
            a=d[column+"_active"].to_numpy(bool)
            w[a]+=weight-W
    w=np.clip(w,.05,.65)
    delta=np.zeros(len(d))
    for short,column in [
        ("E3","E3_opponent_quality"),("E4","E4_offense_defense_matchups"),
        ("E5","E5_home_road_strength")]:
        if short in names:
            active=d[column+"_active"].to_numpy(bool)
            blend=d[column+"_pred"].to_numpy(float)
            alternative=(blend-(1-W)*market)/W
            delta[active]+=(logit(np.clip(alternative[active],1e-12,1-1e-12))-
                            logit(np.clip(old[active],1e-12,1-1e-12)))
    model=expit(logit(np.clip(old,1e-12,1-1e-12))+delta)
    return w*model+(1-w)*market

def summarize(d,p,baseline):
    y=d.home_won.to_numpy(int)
    correct=(p>=.5)==y
    basecorrect=(baseline>=.5)==y
    switched=(p>=.5)!=(baseline>=.5)
    return dict(n=len(d),wins=int(correct.sum()),losses=int((~correct).sum()),
       accuracy=round(float(correct.mean()),6),
       brier=round(float(np.mean((p-y)**2)),7),
       brier_gain=round(float(np.mean((baseline-y)**2-(p-y)**2)),7),
       flips=int(switched.sum()),corrected=int((switched&correct).sum()),
       newly_wrong=int((switched&(~correct)).sum()),
       net_winners=int(correct.sum()-basecorrect.sum()))

def main():
    d=pd.read_csv(DATA,low_memory=False)
    assert len(d)==1658
    assert d.groupby("year").size().to_dict()=={2024:717,2025:720,2026:221}
    assert {x for x in d.columns if x.endswith("_active")} == {
        "E1_close_games_active","E2_disagreement_active",
        "E3_opponent_quality_active","E4_offense_defense_matchups_active",
        "E5_home_road_strength_active","E6_stat_reliability_active"}
    p0=d.testc_baseline.to_numpy(float)
    combos={"official_baseline":[],
            "all_six_selected_2024":["E1","E2","E3","E4","E5","E6"],
            "football_only_E3_E4_E5":["E3","E4","E5"],
            "market_only_E1_E2_E6":["E1","E2","E6"],
            "all_except_E2":["E1","E3","E4","E5","E6"]}
    scores={}
    for label,names in combos.items():
        p=combine(d,names)
        score={}
        for year in (2024,2025,2026):
            mask=d.year.eq(year).to_numpy()
            score[str(year)]=summarize(d[mask],p[mask],p0[mask])
        mask=d.year.eq(2026)&d.week.ge(5)
        score["2026_frozen_W5_6"]=summarize(d[mask],p[mask],p0[mask])
        scores[label]=score
    OUT.write_text(json.dumps({
        "name":"Test E combined effects from six 2024-selected rules",
        "candidate_combination":"Add weight differences of triggered E1/E2/E6 around fixed Test C, cap in 5%-65% V1.5; add V1.5 log-odds deltas of triggered E3/E4/E5. No new fitting.",
        "combinations":combos,
        "scores":scores,
        "limitations":"Combined rules are exploratory; each selected from 2024, and 2025/2026 use retrospective/frozen-proxy inputs, not a genuine newly observed live forecast."
    },indent=2)+"\n")
    print("TEST_E_COMBINED "+json.dumps(scores,sort_keys=True),flush=True)

if __name__=="__main__":main()
