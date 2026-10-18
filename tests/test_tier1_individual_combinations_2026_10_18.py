"""Historical ATS signal audit: each Tier1 advantage, pairs and triples.

Research-only, no live-model changes. Pregame FBS week-by-week metrics are
computed through existing production build_advantages/assess. 2024 trains
2025 holdout, 2024+25 trains 2026 holdout. Outcome is HOME covering ESPN
archived spread; pushes excluded from binary models, kept in coverage.
"""
import json
import math
import unittest
from itertools import combinations
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit

from matchup_advantages import build_advantages, assess

YEARS=(2024,2025,2026)
LABELS=("Run matchup","Pass matchup","Run defense","Pass defense","Turnover margin")
URLS={
    "schedule":"https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{year}.csv",
    "boxes":"https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_{year}.csv",
    "market":"https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_betting/betting_{year}.csv",
}
BASE=("spread","abs_spread","elo_gap","abs_elo_gap","week","p4")
PENALTY=8.
COMBOS=[(i,) for i in range(5)]+list(combinations(range(5),2))+list(combinations(range(5),3))
def source(item):
    name,url=item
    with urlopen(Request(url,headers={"User-Agent":"SaturdayForecast-ATSFeatureAudit/1.0"}),timeout=110) as r: raw=r.read()
    print("FEED",name,"bytes",len(raw),flush=True)
    return name,pd.read_csv(BytesIO(raw),low_memory=False)

def yes(s):
    return s.astype(str).str.lower().str.strip().isin(["true","t","1","1.0","yes","y"])

def qualify(year, feeds):
    s=feeds[f"{year}_schedule"].copy()
    b=feeds[f"{year}_boxes"]
    m=feeds[f"{year}_market"].copy()
    for col in ("game_id","week","home_id","away_id","home_points","away_points","home_pregame_elo","away_pregame_elo"):
        s[col]=pd.to_numeric(s[col],errors="coerce")
    s=s[s.season_type.astype(str).str.lower().eq("regular")
        &s.home_division.astype(str).str.lower().eq("fbs")
        &s.away_division.astype(str).str.lower().eq("fbs")].copy()
    s["is_final"]=yes(s.completed)
    s["neutral"]=yes(s.neutral_site)
    s=s.dropna(subset=["game_id","week","home_id","away_id"])
    if s.game_id.duplicated().any(): raise AssertionError("Nonunique schedule game_id")
    m["game_id"]=pd.to_numeric(m.game_id,errors="coerce")
    m["home_team_spread"]=pd.to_numeric(m.home_team_spread,errors="coerce")
    m=m[yes(m.game_spread_available)&m.game_id.notna()&m.home_team_spread.notna()].copy()
    if "odds_source" in m:
        m=m[~m.odds_source.astype(str).str.lower().eq("default")]
    if m.game_id.duplicated().any():
        m=m[~m.game_id.isin(m.loc[m.game_id.duplicated(False),"game_id"])]
    lines=dict(zip(m.game_id.astype(int),m.home_team_spread.astype(float)))
    rows=[];coverage={"final_fbs":int(s.is_final.sum()),"metric_valid":0,"line_missing":0,"pregame_elo_missing":0}
    for week in sorted(s.week.dropna().astype(int).unique()):
        if week<2: continue
        adv=build_advantages(s,b,week)
        target=s[s.week.eq(week)&s.is_final&~s.neutral&s.home_points.notna()&s.away_points.notna()]
        for _,g in target.iterrows():
            gid=int(g.game_id)
            a=assess(adv.get(str(gid),{}),"home")
            if not a:continue
            coverage["metric_valid"]+=1
            spread=lines.get(gid)
            if spread is None:
                coverage["line_missing"]+=1;continue
            if pd.isna(g.home_pregame_elo) or pd.isna(g.away_pregame_elo):
                coverage["pregame_elo_missing"]+=1;continue
            v=[int(x=="Advantage") for x in a["outcomes"]]
            ats=float(g.home_points-g.away_points+spread)
            rows.append({
                "year":year,"week":week,"game_id":gid,
                "home":str(g.home_team),"away":str(g.away_team),
                "spread":float(spread),"elo_gap":float(g.home_pregame_elo-g.away_pregame_elo),
                "p4":int(adv[str(gid)]["group"]=="P4"),"count":sum(v),
                "ats_margin":ats,"result":"W" if ats>1e-8 else "L" if ats< -1e-8 else "P",
                **{f"a{i}":v[i] for i in range(5)}
            })
    df=pd.DataFrame(rows)
    print("BUILT",year,coverage,"rows",len(df),flush=True)
    if len(df)<80:raise ValueError("Sparse data "+str(year))
    return df,coverage

def summarize(df):
    w=int(df.result.eq("W").sum());l=int(df.result.eq("L").sum());p=int(df.result.eq("P").sum())
    return {"n":int(len(df)),"W":w,"L":l,"P":p,
            "ATS_pct":round(100*w/(w+l),2) if w+l else None,
            "mean_spread":round(float(df.spread.mean()),2) if len(df) else None,
            "mean_elo":round(float(df.elo_gap.mean()),1) if len(df) else None}

def xy(df, selected=(), interaction=False):
    x=np.column_stack([
        np.ones(len(df)),
        df.spread.to_numpy(float)/10.,
        np.abs(df.spread.to_numpy(float))/10.,
        df.elo_gap.to_numpy(float)/200.,
        np.abs(df.elo_gap.to_numpy(float))/200.,
        df.week.to_numpy(float)/10.,
        df.p4.to_numpy(float)
    ])
    extra=[df[f"a{i}"].to_numpy(float) for i in selected]
    if interaction and len(selected)>=2:
        extra.extend(
            np.prod(np.stack([df[f"a{i}"].to_numpy(float) for i in idx],axis=1),axis=1)
            for k in range(2,len(selected)+1) for idx in combinations(selected,k)
        )
    if extra:x=np.column_stack([x,*extra])
    return x

def model(train,valid,selected=(),interaction=False):
    tr=xy(train,selected,interaction);te=xy(valid,selected,interaction)
    y=train.result.eq("W").to_numpy(float)
    pen=np.r_[0.,np.full(tr.shape[1]-1,PENALTY)]
    def loss(beta):
        v=tr@beta
        return float(np.logaddexp(0,v).sum()-y@v+0.5*np.sum(pen*beta**2))
    def grad(beta):
        return tr.T@(expit(tr@beta)-y)+pen*beta
    fit=minimize(loss,np.zeros(tr.shape[1]),jac=grad,method="BFGS",options={"maxiter":300})
    if not np.isfinite(fit.x).all():raise ArithmeticError("Nonfinite logistic fit")
    return expit(te@fit.x),fit.x

def brier(y,p):
    return round(float(np.mean((p-y)**2)),6) if len(y) else None

def ll(y,p):
    if not len(y):return None
    p=np.clip(p,1e-5,1-1e-5)
    return round(float(np.mean(-y*np.log(p)-(1-y)*np.log(1-p))),6)

def cohort(df,c):
    return df[np.logical_and.reduce([df[f"a{i}"].eq(1).to_numpy() for i in c])]

def empirical(df):
    out={}
    for c in COMBOS:
        name="+".join(LABELS[i] for i in c)
        subset=cohort(df,c)
        out[name]=summarize(subset)
        out[name]["indices"]=list(c)
        out[name]["without"]=summarize(df[~df.index.isin(subset.index)])
    return out

def single_holdout(train,test):
    y=test.result.eq("W").to_numpy(float)
    p_base,base_coef=model(train,test)
    out={"n":len(test),"market_50":{"brier":brier(y,np.full(len(test),.5)), "logloss":ll(y,np.full(len(test),.5))},
         "baseline":{"brier":brier(y,p_base),"logloss":ll(y,p_base)},
         "single":{}, "pair":{}, "triple":{}}
    for c in COMBOS:
        p,b=model(train,test,c,False)
        key="+".join(LABELS[i] for i in c)
        d={"brier":brier(y,p),"delta_brier":round(float(np.mean((p-y)**2-(p_base-y)**2)),6),
           "logloss":ll(y,p),"adjusted_main_coefficients":[round(float(v),4) for v in b[-len(c):]],
           "feature_on":summarize(cohort(test,c))}
        cat={1:"single",2:"pair",3:"triple"}[len(c)]
        out[cat][key]=d
    p5,b5=model(train,test,tuple(range(5)),False)
    p5int,b5int=model(train,test,tuple(range(5)),True)
    out["all_five_main_effects"]={"brier":brier(y,p5),"delta_brier":round(float(np.mean((p5-y)**2-(p_base-y)**2)),6),
                                   "logloss":ll(y,p5),"coefficients":[round(float(v),4) for v in b5[-5:]]}
    out["all_five_with_interactions"]={"brier":brier(y,p5int),"delta_brier":round(float(np.mean((p5int-y)**2-(p_base-y)**2)),6),
                                   "logloss":ll(y,p5int),"model_columns":len(b5int)}
    # True synergy check: two main effects alone vs both plus interaction.
    out["pairs_interaction_increment"]={}
    for c in combinations(range(5),2):
        p_main,b_main=model(train,test,c,False)
        p_inter,b_inter=model(train,test,c,True)
        name="+".join(LABELS[i] for i in c)
        out["pairs_interaction_increment"][name]={
            "brier_main":brier(y,p_main),"brier_with_interaction":brier(y,p_inter),
            "delta_from_main":round(float(np.mean((p_inter-y)**2-(p_main-y)**2)),6),
            "interaction_coeff":round(float(b_inter[-1]),4)}
    return out

def analyze():
    with ThreadPoolExecutor(max_workers=9) as pool:
        feeds=dict(pool.map(source,[
            (f"{yr}_{kind}",url.format(year=yr))
            for yr in YEARS for kind,url in URLS.items()
        ]))
    years={};cover={}
    for yr in YEARS:
        years[yr],cover[yr]=qualify(yr,feeds)
    pooled=pd.concat(list(years.values()),ignore_index=True)
    report={"method":"The 5 production home advantages separately; all 10 pairs + 10 triples; point-spread, Elo, week and conference controlled; ATS home side, not waterfall priority",
            "cautions":"Archived ESPN lines not immutable original prices; same-year data not used for fitted holdout; selection among 25 combinations risks multiple comparisons",
            "coverage":cover,
            "whole_sample":summarize(pooled),
            "single_and_combo_raw":{str(yr):empirical(df) for yr,df in
                ((2024,years[2024]),(2025,years[2025]),(2026,years[2026]),("all",pooled))},
            "holdouts":{}}
    for yr,train in ((2025,years[2024]),(2026,pd.concat([years[2024],years[2025]],ignore_index=True))):
        test=years[yr]
        train=train[train.result.ne("P")].copy()
        test=test[test.result.ne("P")].copy()
        report["holdouts"][str(yr)]=single_holdout(train,test)
    # Prospectively evaluate top pair chosen based solely on 2024/25, not 2026.
    train=pooled[pooled.year.isin([2024,2025])&pooled.result.ne("P")].copy()
    te=years[2026][years[2026].result.ne("P")].copy()
    raw=empirical(train)
    eligible=[(k,v) for k,v in raw.items() if len(v["indices"])==2 and v["n"]>=40]
    # Primary candidate selected by historical ATS uplift vs entire cohort.
    chosen=max(eligible,key=lambda kv:(kv[1]["ATS_pct"]-summarize(train)["ATS_pct"])) if eligible else None
    report["frozen_candidate_selected_from_2024_2025"]=(
        {"name":chosen[0],"train_summary":chosen[1],
        "2026_validation":summarize(cohort(te,chosen[1]["indices"]))} if chosen else None)
    # Compute the pairwise interaction model in 2025 and 2026 holdouts to
    # distinguish coincidence from synergy.
    print("TIER1_INDIVIDUAL_COMBO_REPORT="+json.dumps(report,allow_nan=False),flush=True)
    return report

class Tier1IndividualCombinationTest(unittest.TestCase):
    def test_historical(self):
        report=analyze()
        self.assertGreater(report["whole_sample"]["n"],1000)
        self.assertGreater(report["holdouts"]["2025"]["n"],400)
        self.assertGreater(report["holdouts"]["2026"]["n"],150)
        self.assertEqual(len(report["holdouts"]["2025"]["pair"]),10)
        self.assertEqual(len(report["holdouts"]["2025"]["triple"]),10)

if __name__=="__main__":
    unittest.main(verbosity=2)
