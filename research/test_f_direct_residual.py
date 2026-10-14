"""Test F2: independent matchup residual directly correcting Test C.

Reads actual prior-week FBS-box metrics, real matched quotes, and outcomes from
Test F's reproducible game-level file. Coefficients are selected from a
predefined candidate set on 2024 Brier; later years are not used for tuning.
Purely historical research, no app/tier changes.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import expit, logit
from scipy.stats import binomtest

ROOT=Path(__file__).resolve().parents[1]
IN=ROOT/"research/test_f_matchups_games.csv"
OUT=ROOT/"research/test_f_direct_residual_results.json"
CHANGED=ROOT/"research/test_f_direct_changed_games.csv"
FAMILIES=("run","completion","passing_ypa","run_plus_completion",
          "run_plus_ypa","all_three")
COEFFS=(-.40,-.30,-.20,-.10,-.05,0.,.05,.10,.20,.30,.40,.50,.75)
MIN_GAMES=(1,2,3,4)

def signal(rows,name):
    run=np.clip(rows.run_diff.fillna(0).to_numpy(dtype=float)/2.,-3,3)
    completion=np.clip(rows.comp_diff.fillna(0).to_numpy(dtype=float)/.15,-3,3)
    ypa=np.clip(rows.ypa_diff.fillna(0).to_numpy(dtype=float)/3.,-3,3)
    return {
      "run":run,"completion":completion,"passing_ypa":ypa,
      "run_plus_completion":(run+completion)/2,
      "run_plus_ypa":(run+ypa)/2,
      "all_three":(run+completion+ypa)/3}[name]

def forecast(rows,name,min_games,beta):
    yes=rows.eligible.to_numpy(bool)&rows.n_min.ge(min_games).to_numpy(bool)
    z=signal(rows,name)
    p=expit(logit(np.clip(rows.p_testc.to_numpy(float),1e-9,1-1e-9))+
      np.where(yes,beta*z,0.))
    return p,yes

def metrics(rows,p):
    y=rows.y.to_numpy(dtype=int)
    orig=rows.p_testc.to_numpy(float)
    selected=(p>=.5)==y
    old=(orig>=.5)==y
    change=(p>=.5)!=(orig>=.5)
    fix=int((change&selected).sum())
    broken=int((change&(~selected)).sum())
    return {
      "n":len(rows),"wins":int(selected.sum()),"losses":int((~selected).sum()),
      "accuracy":round(float(selected.mean()),6),
      "brier":round(float(np.mean((p-y)**2)),7),
      "brier_gain":round(float(np.mean((orig-y)**2-(p-y)**2)),7),
      "log_loss":round(float(np.mean(
        -y*np.log(np.clip(p,1e-12,1-1e-12))-
        (1-y)*np.log(np.clip(1-p,1e-12,1-1e-12)))),7),
      "winner_switches":fix+broken,"errors_fixed":fix,
      "new_errors":broken,"net_new_winners":fix-broken,
      "paired_two_sided_p":round(float(binomtest(fix,fix+broken,.5).pvalue),6) if fix+broken else 1.
    }

def main():
    rows=pd.read_csv(IN,low_memory=False)
    assert len(rows)==1658
    assert rows.groupby("year").size().to_dict()=={2024:717,2025:720,2026:221}
    assert len(rows[rows.year.eq(2026)&rows.week.isin([5,6])])==112
    assert not rows.duplicated(["year","id"]).any()
    assert rows.p_testc.between(0,1,inclusive="neither").all()
    assert rows.y.isin([0,1]).all()
    sets={
     "2024_development":rows[rows.year.eq(2024)],
     "2025_temporal_validation":rows[rows.year.eq(2025)],
     "2026_weeks3_6":rows[rows.year.eq(2026)],
     "2026_frozen_weeks5_6":rows[rows.year.eq(2026)&rows.week.isin([5,6])]
    }
    baseline={key:metrics(sub,sub.p_testc.to_numpy(float)) for key,sub in sets.items()}
    outputs={}
    chosen={}
    for family in FAMILIES:
        candidates={}
        for games in MIN_GAMES:
            for beta in COEFFS:
                name=f"min{games}_beta{beta:+.2f}"
                scores={key:metrics(sub,forecast(sub,family,games,beta)[0])
                    for key,sub in sets.items()}
                scores["configuration"]={"minimum_prior_fbs_games":games,
                    "extra_log_odds_coefficient":beta}
                candidates[name]=scores
        # 2024 Brier only, then 2024 wins then prefer least-complex absolute beta
        selected=min(candidates,key=lambda key:(
            candidates[key]["2024_development"]["brier"],
            -candidates[key]["2024_development"]["wins"],
            abs(candidates[key]["configuration"]["extra_log_odds_coefficient"]),key))
        outputs[family]={"selected_from_2024":selected,
            "selected_scores":candidates[selected],"candidates":candidates}
        chosen[family]=outputs[family]["selected_scores"]
    # Dedicated minimal passing-ypa residual is the 2024-selected best of this
    # direct Test C family, NOT a new 2025- or 2026-fitted coefficient.
    ypa=outputs["passing_ypa"]["selected_scores"]["configuration"]
    p,mask=forecast(rows,"passing_ypa",ypa["minimum_prior_fbs_games"],
        ypa["extra_log_odds_coefficient"])
    changed=rows.loc[(p>=.5)!=(rows.p_testc.to_numpy(float)>=.5),
        ["year","week","id","game","y","p_testc","ypa_diff"]].copy()
    changed["test_f_probability"]=p[(p>=.5)!=(rows.p_testc.to_numpy(float)>=.5)]
    changed["baseline_correct"]=((changed.p_testc>=.5)==changed.y)
    changed["challenger_correct"]=((changed.test_f_probability>=.5)==changed.y)
    changed.to_csv(CHANGED,index=False)
    assert len(changed)==17
    assert chosen["passing_ypa"]["2024_development"]["wins"]==511
    assert chosen["passing_ypa"]["2025_temporal_validation"]["wins"]==529
    assert chosen["passing_ypa"]["2026_weeks3_6"]["wins"]==170
    assert chosen["passing_ypa"]["2026_frozen_weeks5_6"]["wins"]==78
    report={
      "experiment":"Test F2 direct residual vs market-informed Test C",
      "created_utc":datetime.now(timezone.utc).isoformat(),
      "definition":"P_new=logistic(logit(P_TestC)+beta*clipped_pregame_FBS_matchup_signal). For missing/insufficient prior FBS boxes use unchanged Test C.",
      "source":"research/test_f_matchups_games.csv (reproducibly created by research/test_f_rush_pass_matchups.py)",
      "primary_market_weight":0.8307207305278489,
      "candidate_count":len(FAMILIES)*len(MIN_GAMES)*len(COEFFS),
      "beta_grid":list(COEFFS),
      "min_games_grid":list(MIN_GAMES),
      "baseline":baseline,
      "families":outputs,
      "pass_ypa_game_changes":len(changed),
      "limitations":[
        "Historical years used retrospective current-code V1.5, not contemporaneously frozen predictions.",
        "2026 Weeks5-6 original V1.5 source was frozen; market odds used here are archived DraftKings opening records, rather than guaranteed exact live capture timestamps.",
        "2026 Weeks3-4 V1.5 reconstructions are retrospective, with outcomes never used to build the feature but this is not an independently timed pregame capture.",
        "2024 development selection is in-sample and multiple families/betas/minimum-game values were screened; 2025 is a later check not wholly untouched by previous model work.",
        "The direct residual changes the final market-blended probability. No statistical proof of >0 future winner lift follows from 17 switched games.",
        "Prior FBS team-box statistics include rushing, passing attempts, completions and net pass yards; no reliable pressure or sack fields, so pressure/protection remains untested.",
        "No production, V1.5 components, Test C market blend weights or six waterfall betting tiers are changed."
      ]
    }
    OUT.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print("TEST_F2_DIRECT_RESIDUAL "+json.dumps({
        "baseline":baseline,"selected":{name:{"config":v["configuration"],
          "results":{k:v[k] for k in sets}} for name,v in chosen.items()},
        "passing_ypa_changed":changed.to_dict(orient="records")
      },sort_keys=True),flush=True)

if __name__=="__main__":
    main()
