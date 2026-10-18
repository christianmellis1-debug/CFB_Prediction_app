"""Research only: calibrated cover probabilities vs margin-value Tier 1 flags.

Historical test: train 2024 -> evaluate 2025; train 2024+2025 -> evaluate 2026.
Only prior-week FBS results in predictive features. Existing opponent-adjustment
historical study is imported without changing production code.
"""
import json
import math
import unittest

import numpy as np
import pandas as pd
from scipy.special import ndtr, expit
from scipy.optimize import minimize

from test_opponent_adjustment_historical import (
    YEARS, URLS, fetch_one, feature_games, prepare_schedule,
    reconstruct_tier1, fit_ridge, predict, grade,
)
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPECIFICATIONS=("elo","raw","opponent")
CUTOFFS=(0.50,0.525,0.55,0.60,0.65)
EPS=1e-5

def brier(y,p):
    if len(y)==0: return None
    return round(float(np.mean((p-y)**2)),5)

def logloss(y,p):
    if len(y)==0: return None
    p=np.clip(p,EPS,1-EPS)
    return round(float(np.mean(-y*np.log(p)-(1-y)*np.log(1-p))),5)

def prob_summary(frame,prob_key):
    g=frame[frame["ats_result"].isin(("Win","Loss"))].copy()
    y=g.ats_result.eq("Win").to_numpy(dtype=float)
    p=g[prob_key].to_numpy(dtype=float)
    return {"n":len(g),"brier":brier(y,p),"logloss":logloss(y,p),
            "observed_ats_pct":round(100*float(y.mean()),2) if len(y) else None,
            "mean_probability":round(float(p.mean()),4) if len(p) else None,
            "calibration_bins":[{"p_min":float(lo),"p_max":float(hi),
                  "n":int(((p>=lo)&(p<(hi if hi<1 else 1.000001))).sum()),
                  "avg_p":round(float(p[(p>=lo)&(p<(hi if hi<1 else 1.000001))].mean()),3) if ((p>=lo)&(p<(hi if hi<1 else 1.000001))).sum() else None,
                  "actual":round(float(y[(p>=lo)&(p<(hi if hi<1 else 1.000001))].mean()),3) if ((p>=lo)&(p<(hi if hi<1 else 1.000001))).sum() else None}
                  for lo,hi in [(0.,.4),(.4,.5),(.5,.6),(.6,1.)]]}

def selections(df, probability):
    return {str(t):grade(df[df[probability]>=t]) for t in CUTOFFS}

def sigma_training(training, previous_model, holdout=None):
    # 2025 uses 2024 training residual sigma, 2026 uses 2025
    # out-of-year 2024-trained holdout residuals for calibration.
    ref=holdout if holdout is not None else training
    model=previous_model
    p=predict(model, ref)
    diff=ref.home_margin.to_numpy(dtype=float)-p
    return float(np.sqrt(np.mean(diff**2)))

def fit_logistic(training, predictor="edge_opp"):
    """Use historical candidate picks only, with modest coefficient penalty."""
    g=training[training.ats_result.isin(("Win","Loss"))].copy()
    x=g[predictor].to_numpy(dtype=float)/10
    y=g.ats_result.eq("Win").to_numpy(dtype=float)
    def loss(beta):
        z=beta[0]+beta[1]*x
        prob=np.clip(expit(z),EPS,1-EPS)
        # Constrain overconfident responses; no future-year data.
        return float(np.sum(-y*np.log(prob)-(1-y)*np.log(1-prob))+2.0*beta[1]**2+0.5*beta[0]**2)
    ret=minimize(loss,np.array([0.,0.]),method="BFGS")
    if not ret.success and np.any(~np.isfinite(ret.x)):
        raise ArithmeticError("Calibration did not converge")
    return np.asarray(ret.x,dtype=float)

def report():
    raw=dict(ThreadPoolExecutor(max_workers=9).map(fetch_one,(
        (f"{year}_{kind}",url.format(year=year))
        for year in YEARS for kind,url in URLS.items()
    )))
    rows={}; features={}; picks={}; cover={}
    for year in YEARS:
        s=prepare_schedule(raw[f"{year}_schedule"])
        features[year]=feature_games(s)
        picks[year],cover[year]=reconstruct_tier1(s,raw[f"{year}_box"],raw[f"{year}_market"])
        print("PREP",year,len(features[year]),len(picks[year]),flush=True)

    # Train separate models, never on the evaluation season.
    models2024={m:fit_ridge(features[2024],m) for m in SPECIFICATIONS}
    models2024_25={m:fit_ridge(pd.concat([features[2024],features[2025]],ignore_index=True),m) for m in SPECIFICATIONS}

    # Sigma based only on earlier years. For 2026 use a 2025
    # out-of-season error distribution from 2024 trained model.
    sigma25={m:sigma_training(features[2024],models2024[m]) for m in SPECIFICATIONS}
    sigma26={m:sigma_training(features[2024],models2024[m],features[2025]) for m in SPECIFICATIONS}
    # Historical calibration candidates: fitting same-year predictions is
    # optimistic. 2025 calibration uses solely 2024; 2026 calibration uses
    # 2024 candidates and true 2025 out-of-season margin estimates.
    train_calibration={}
    for year in (2024,2025):
        fm=features[year].copy()
        mm=models2024 if year==2024 else models2024
        for method in SPECIFICATIONS:
            fm["pred_"+method]=predict(mm[method],fm)
        f=picks[year].merge(fm[["event_id","pred_opponent"]],on="event_id",validate="one_to_one").dropna(subset=["pred_opponent"])
        f["edge_opp"]=f.pred_opponent+f.spread
        train_calibration[year]=f

    output={"notes":"Research-only, archived ESPN spreads can differ from frozen pregame lines; no ATS ROI claims.","training":{
        "2025":"2024","2026":"2024+2025",
        "sigma_calibration_2025":"residuals on 2024 training games",
        "sigma_calibration_2026":"2025 out-of-year residuals from 2024 model",
        "logistic_calibration_2025":"2024 Tier1 candidates (2024 in-sample margins)",
        "logistic_calibration_2026":"2024 and 2025 Tier1 candidates (2025 cross-season margins)"},
        "coverage":cover,"years":{},"locked_week7":{}}

    for year in (2025,2026):
        modelset=models2024 if year==2025 else models2024_25
        sdset=sigma25 if year==2025 else sigma26
        fm=features[year].copy()
        for m in SPECIFICATIONS:fm["pred_"+m]=predict(modelset[m],fm)
        usable=picks[year].merge(fm[["event_id"]+["pred_"+m for m in SPECIFICATIONS]],on="event_id",validate="one_to_one")
        usable=usable.dropna(subset=["pred_"+m for m in SPECIFICATIONS]).copy()
        usable["p_market"]=.5
        for m in SPECIFICATIONS:
            usable["edge_"+m]=usable["pred_"+m]+usable.spread
            usable["p_"+m]=ndtr(usable["edge_"+m]/sdset[m])
        trainer=(train_calibration[2024] if year==2025 else pd.concat([train_calibration[2024],train_calibration[2025]],ignore_index=True))
        logit=fit_logistic(trainer)
        usable["p_logistic"]=expit(logit[0]+logit[1]*usable.edge_opponent/10)
        label="year_"+str(year)
        output["years"][label]={
            "n":len(usable),
            "logistic_intercept":round(float(logit[0]),4),
            "logistic_edge_coefficient_per_10_points":round(float(logit[1]),4),
            "estimated_residual_sd":{m:round(float(sdset[m]),3) for m in SPECIFICATIONS},
            "baseline":grade(usable),
            "probability_comparison":{
                key:prob_summary(usable,key)
                for key in ("p_market","p_elo","p_raw","p_opponent","p_logistic")
            },
            "selection_comparison":{
                key:selections(usable,key)
                for key in ("p_elo","p_raw","p_opponent","p_logistic")
            },
        }
        if year==2026:
            archive=json.loads((ROOT/"data/value_archive_2026.json").read_text())
            locked={int(k):v for k,v in archive["snapshots"].items()
                    if v.get("week")==7 and v.get("selected") is True and v.get("Value Stage")==1}
            results=archive["results"]
            frozen=usable[usable.event_id.isin(locked)].copy()
            frozen["spread"]=frozen.event_id.map(lambda gid:float(locked[int(gid)]["Value Line"]))
            frozen["ats_margin"]=frozen.apply(
                lambda r: float(results[str(int(r.event_id))]["home_score"])
                          -float(results[str(int(r.event_id))]["away_score"])
                          +float(locked[int(r.event_id)]["Value Line"]),axis=1)
            frozen["ats_result"]=frozen.ats_margin.map(lambda x:"Win" if x>1e-8 else "Loss" if x<-1e-8 else "Push")
            for m in SPECIFICATIONS:
                frozen["edge_"+m]=frozen["pred_"+m]+frozen.spread
                frozen["p_"+m]=ndtr(frozen["edge_"+m]/sdset[m])
            frozen["p_logistic"]=expit(logit[0]+logit[1]*frozen.edge_opponent/10)
            output["locked_week7"]={
                "locked_n":len(locked),"matched":len(frozen),
                "baseline":grade(frozen),
                "probs":{k:prob_summary(frozen,k) for k in ("p_market","p_elo","p_raw","p_opponent","p_logistic")},
                "selection":{k:selections(frozen,k) for k in ("p_elo","p_raw","p_opponent","p_logistic")},
                "picks":[{
                    "pick":r.home,"line":float(r.spread),"result":r.ats_result,
                    "margin_prediction":round(float(r.pred_opponent),1),
                    "edge":round(float(r.edge_opponent),1),
                    "cover_probability":round(float(r.p_opponent),3),
                    "logistic_cover_probability":round(float(r.p_logistic),3),
                } for _,r in frozen.iterrows()]
            }

    print("TIER1_COVER_PROBABILITY_REPORT="+json.dumps(output,allow_nan=False),flush=True)
    return output

class CoverProbabilityHistoricalTest(unittest.TestCase):
    def test_cover_probability_holdouts(self):
        x=report()
        self.assertEqual(x["locked_week7"]["matched"],10)
        self.assertGreater(x["years"]["year_2025"]["n"],30)
        self.assertGreater(x["years"]["year_2026"]["n"],15)

if __name__=="__main__":
    unittest.main(verbosity=2)
