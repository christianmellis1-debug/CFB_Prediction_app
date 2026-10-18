"""Controlled comparison of 4/6, 5/6 and 6/6 home-side matchup advantages.

Research branch only, no production changes. Each group means home field plus
respectively three, four, or five favorable statistics from Saturday Forecast's
EXACT pregame build_advantages/assess logic.

Controls: archived home-relative spread, pregame Elo gap, P4/G6 and week;
year-separated 2024->2025 and 2024+25->2026 predictive holdouts.
"""
import json
import math
import unittest
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit
from scipy.stats import norm
from matchup_advantages import assess, build_advantages

YEARS=(2024,2025,2026)
URLS={
    "schedule":"https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{year}.csv",
    "box":"https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_{year}.csv",
    "betting":"https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_betting/betting_{year}.csv",
}
P4={"ACC","Big Ten","Big 12","SEC"}
G6={"American Athletic","Conference USA","Mid-American","Mountain West","Sun Belt","Pac-12"}
FEATURE_BASE=("spread_magnitude","spread_favorite","elo_gap","p4","week_index")
FEATURE_ADV=FEATURE_BASE+("five","six")
SEED=20261018
EPS=1e-8

def load(item):
    name,url=item
    with urlopen(Request(url,headers={"User-Agent":"SaturdayForecast-AdvantageControl/1.0"}),timeout=105) as f:
        b=f.read()
    print("FEED",name,len(b),flush=True)
    return name,pd.read_csv(BytesIO(b),low_memory=False)

def truth(series):
    return series.astype(str).str.strip().str.lower().isin(("true","t","1","1.0","yes","y"))

def group(conference,team):
    if str(team).strip().casefold()=="notre dame":return "P4"
    if conference in P4:return "P4"
    if conference in G6:return "G6"
    return None

def get_lines(betting):
    b=betting.copy()
    for c in ("game_id","home_team_spread"):
        b[c]=pd.to_numeric(b[c],errors="coerce")
    b=b[truth(b.game_spread_available)&b.game_id.notna()&b.home_team_spread.notna()]
    if "odds_source" in b:
        b=b[~b.odds_source.astype(str).str.lower().eq("default")]
    conflicts=set(b.loc[b.duplicated("game_id",keep=False),"game_id"].astype(int))
    b=b[~b.game_id.isin(conflicts)]
    return dict(zip(b.game_id.astype(int),b.home_team_spread.astype(float)))

def spread_bin(spread):
    if spread>0:return "home-underdog"
    magnitude=abs(spread)
    if magnitude<=3:return "favorite-0to3"
    if magnitude<=6.5:return "favorite-3.5to6.5"
    if magnitude<=13.5:return "favorite-7to13.5"
    if magnitude<=20.5:return "favorite-14to20.5"
    return "favorite-21plus"

def build_cohort(year):
    feeds=dict(ThreadPoolExecutor(max_workers=3).map(load,[
        (key+"_"+str(year),template.format(year=year)) for key,template in URLS.items()
    ]))
    s=feeds["schedule_"+str(year)].copy()
    for c in ("game_id","season","week","home_id","away_id","home_points",
              "away_points","home_pregame_elo","away_pregame_elo"):
        s[c]=pd.to_numeric(s[c],errors="coerce")
    s=s[
        s.season_type.astype(str).str.lower().eq("regular")
        & s.home_division.astype(str).str.lower().eq("fbs")
        & s.away_division.astype(str).str.lower().eq("fbs")
    ].copy()
    s=s.dropna(subset=["game_id","week","home_id","away_id"])
    if s.game_id.duplicated().any():raise AssertionError("Duplicate FBS game IDs")
    s["final"]=truth(s.completed)&s.home_points.notna()&s.away_points.notna()
    s["neutral"]=truth(s.neutral_site)
    lines=get_lines(feeds["betting_"+str(year)])
    boxes=feeds["box_"+str(year)]
    all_complete=int(s.final.sum())
    elig=0; missing_quote=0; missing_elo=0; no_history=0; records=[]
    for week in sorted(set(s.week.astype(int))):
        if week<2:continue
        checks=build_advantages(s,boxes,week)
        week_games=s[s.week.eq(week)&s.final&~s.neutral]
        for _,g in week_games.iterrows():
            gid=int(g.game_id)
            rec=checks.get(str(gid),{})
            if rec.get("status")!="ok":
                no_history+=1
                continue
            # 4/6 = three statistical edges+home field, 5/6 = four,
            # 6/6 = five; the current Tier 1 uses ONLY 6/6.
            advantages=assess(rec,"home")
            if advantages is None or advantages["count"] not in (3,4,5):
                continue
            elig+=1
            spread=lines.get(gid)
            if spread is None:
                missing_quote+=1
                continue
            gap=float(g.home_pregame_elo)-float(g.away_pregame_elo)
            if not np.isfinite(gap):
                missing_elo+=1
            margin=float(g.home_points)-float(g.away_points)
            ats=margin+spread
            records.append({
                "year":year,"week":int(week),"game_id":gid,
                "home":str(g.home_team),"away":str(g.away_team),
                "group":rec["group"],"advantages":int(advantages["count"])+1,
                "spread":float(spread),"spread_bin":spread_bin(float(spread)),
                "elo_gap":gap,"actual_margin":margin,"ats_margin":ats,
                "result":"W" if ats>EPS else "L" if ats<-EPS else "P",
            })
    print("YEAR",year,"completed",all_complete,"eligible",elig,"priced",len(records),flush=True)
    return pd.DataFrame(records),{
        "completed_fbs":all_complete,"qualifying_4to6":elig,
        "priced":len(records),"missing_spread":missing_quote,
        "missing_elo":missing_elo,"outside_or_missing_history_or_below_4of6":no_history,
    }

def record(rows):
    if len(rows)==0:return {"n":0,"wins":0,"losses":0,"pushes":0,"rate":None}
    w=int((rows.result=="W").sum());l=int((rows.result=="L").sum());p=int((rows.result=="P").sum())
    return {"n":int(len(rows)),"wins":w,"losses":l,"pushes":p,
            "rate":round(w/(w+l),4) if w+l else None,
            "ats_margin_avg":round(float(rows.ats_margin.mean()),2),
            "avg_abs_spread":round(float(rows.spread.abs().mean()),2),
            "avg_elo_gap":round(float(rows.elo_gap.mean()),1),
            "p4_fraction":round(float((rows.group=="P4").mean()),3),
            "fav_fraction":round(float((rows.spread<=0).mean()),3)}

def results_by_group(frame):
    return {str(k):record(frame[frame.advantages.eq(k)]) for k in (4,5,6)}

def add_predictors(f):
    f=f.copy()
    f["spread_magnitude"]=f.spread.abs()/10.0
    f["spread_favorite"]=(f.spread<=0).astype(float)
    f["elo_gap"]=f.elo_gap/100.0
    f["p4"]=(f.group=="P4").astype(float)
    f["week_index"]=(f.week-8)/7.0
    f["five"]=(f.advantages==5).astype(float)
    f["six"]=(f.advantages==6).astype(float)
    return f

def fit_logit(frame,columns,regularization=0.5):
    a=frame[frame.result.isin(("W","L"))].dropna(subset=list(columns))
    X=np.column_stack([np.ones(len(a)),a[list(columns)].to_numpy(dtype=float)])
    y=(a.result=="W").to_numpy(dtype=float)
    def f(beta):
        z=X @ beta
        # logaddexp avoids overflow in logistic likelihood
        return float(np.logaddexp(0,z).sum()-np.dot(y,z)+0.5*regularization*np.dot(beta[1:],beta[1:]))
    def jac(beta):
        p=expit(X@beta)
        grad=X.T@(p-y)
        grad[1:]+=regularization*beta[1:]
        return grad
    opt=minimize(f,np.zeros(X.shape[1]),jac=jac,method="BFGS",options={"gtol":1e-6,"maxiter":250})
    if not np.isfinite(opt.fun):raise AssertionError("Logistic model failed")
    return opt.x

def score_on(train,test):
    a=test[test.result.isin(("W","L"))].dropna(subset=list(FEATURE_ADV))
    y=(a.result=="W").to_numpy(dtype=float)
    out={"n":int(len(a))}
    for name,cols in (("book_50",()),("baseline",FEATURE_BASE),("plus_advantages",FEATURE_ADV)):
        if name=="book_50":p=np.full(len(a),0.5)
        else:
            coef=fit_logit(train,cols)
            p=expit(coef[0]+a[list(cols)].to_numpy(dtype=float)@coef[1:])
            out[name+"_coefficients"]=dict(zip(["intercept"]+list(cols),[round(float(t),4) for t in coef]))
        p=np.clip(p,EPS,1-EPS)
        out[name]={"brier":round(float(np.mean((p-y)**2)),5),
                   "logloss":round(float(np.mean(-y*np.log(p)-(1-y)*np.log(1-p))),5),
                   "mean_p":round(float(p.mean()),3)}
    out["brier_delta_from_advantages"]=round(out["plus_advantages"]["brier"]-out["baseline"]["brier"],5)
    return out

def stratified(frame):
    # Spread-matched comparison with Elo rating bins, conference group and
    # year. Report only cells where 6/6 and at least one 4/5 control exist.
    f=frame.copy()
    f["elo_bin"]=pd.cut(f.elo_gap,[-float("inf"),0,150,300,float("inf")],
        labels=["elo-negative","elo-0to149","elo-150to299","elo-300plus"],right=False)
    cells=[]
    for key,part in f.groupby(["year","spread_bin","elo_bin","group"],observed=True):
        six=part[part.advantages==6]
        controls=part[part.advantages.isin((4,5))]
        if len(six)<1 or len(controls)<1:continue
        w6=(six.result=="W").sum();n6=six.result.isin(("W","L")).sum()
        wc=(controls.result=="W").sum();nc=controls.result.isin(("W","L")).sum()
        if not n6 or not nc:continue
        cells.append({"key":"|".join(map(str,key)),"n6":int(n6),"ncontrol":int(nc),
            "rate6":float(w6/n6),"rate_control":float(wc/nc)})
    n=sum(x["n6"] for x in cells)
    return {
        "matched_cells":len(cells),"six_games_with_controls":n,
        "six_total":int((f.advantages==6).sum()),
        "controlled_rate":round(sum(c["n6"]*c["rate_control"] for c in cells)/n,4) if n else None,
        "six_rate_matched":round(sum(c["n6"]*c["rate6"] for c in cells)/n,4) if n else None,
        "difference_pp":round(100*sum(c["n6"]*(c["rate6"]-c["rate_control"]) for c in cells)/n,2) if n else None,
        "high_weight_cells":sorted(cells,key=lambda x:-x["n6"])[:8],
    }

def bootstrap_difference(frame,runs=3000):
    # Naive year-stratified bootstrap: game rows are resampled within year,
    # but not across future/earlier seasons. Does not correct for clustered
    # team dependence. Show uncertainty, NOT a definitive causal estimate.
    f=frame[frame.result.isin(("W","L"))]
    rng=np.random.default_rng(20261018)
    groups={y:f[f.year==y] for y in sorted(f.year.unique())}
    diffs=[]
    for i in range(runs):
        parts=[]
        for y,part in groups.items():
            take=rng.integers(0,len(part),size=len(part))
            parts.append(part.iloc[take])
        a=pd.concat(parts,ignore_index=True)
        six=a[a.advantages==6];control=a[a.advantages.isin((4,5))]
        if not len(six) or not len(control):continue
        diffs.append(float((six.result=="W").mean()-(control.result=="W").mean()))
    p= [float(np.percentile(diffs,k)) for k in (2.5,50,97.5)]
    return {"difference_pp":round(100*p[1],2),"lower_95_pp":round(100*p[0],2),
            "upper_95_pp":round(100*p[2],2),"bootstrap_draws":len(diffs)}

def main():
    with ThreadPoolExecutor(max_workers=3) as pool:
        yearsets=list(pool.map(build_cohort,YEARS))
    coverage={str(y):cov for y,(_,cov) in zip(YEARS,yearsets)}
    allf=pd.concat([f for f,_ in yearsets],ignore_index=True)
    allf=add_predictors(allf)
    if not (allf.advantages.isin((4,5,6)).all()):
        raise AssertionError("unexpected advantage count")
    yearly={str(y):results_by_group(allf[allf.year==y]) for y in YEARS}
    yearly["2024-2025"]=results_by_group(allf[allf.year.isin((2024,2025))])
    yearly["all"]=results_by_group(allf)

    # Distribution of outcomes within the same home-spread bins.
    by_spread={}
    for b in ["home-underdog","favorite-0to3","favorite-3.5to6.5",
              "favorite-7to13.5","favorite-14to20.5","favorite-21plus"]:
        row=allf[allf.spread_bin.eq(b)]
        by_spread[b]=results_by_group(row)
    years_2024_25=allf[allf.year<=2025]
    predictive={
        "2024_train_2025_test":score_on(allf[allf.year==2024],allf[allf.year==2025]),
        "2024_2025_train_2026_test":score_on(years_2024_25,allf[allf.year==2026]),
    }
    adjusted_cohort=allf.dropna(subset=["elo_gap"])
    full=fit_logit(adjusted_cohort,FEATURE_ADV)
    full_coef=dict(zip(["intercept"]+list(FEATURE_ADV),[round(float(v),4) for v in full]))
    report={
        "definition":"home field plus 3/4/5 favorable metrics gives 4/6,5/6,6/6",
        "selection_note":"All games scored home ATS regardless of whether home team is favorite; not the app's alternative tier ordering",
        "coverage":coverage,"yearly":yearly,
        "by_home_spread":by_spread,
        "controlled_holdout":predictive,
        "all_year_controlled_logit_coefficients":full_coef,
        "full_sample_six_vs_4_5":{
            "2024_2025":bootstrap_difference(years_2024_25),
            "all_years":bootstrap_difference(allf),
        },
        "matched_spread_elo_year_group":{
            "2024_2025":stratified(years_2024_25.dropna(subset=["elo_gap"])),
            "all":stratified(adjusted_cohort),
        },
        "year_2026_first7":results_by_group(allf[allf.year.eq(2026)&allf.week.le(7)]),
        "n_total":len(allf),
        "cautions":[
            "Retrospective reconstructions use archived ESPN-derived line feeds, not locked original book lines.",
            "Production tiers have waterfall priority; 4/6 and 5/6 cohorts are research controls, not current Tier 1 picks.",
            "Effect estimates are association conditional on spread/Elo, not randomized treatment effects.",
            "Bootstrap does not account for multiple teams or within-season dependencies.",
            "Brier/logloss holdouts test incremental signal across seasons without optimizing selection thresholds.",
        ]
    }
    print("TIER1_ADVANTAGE_CONTROLS_REPORT="+json.dumps(report,allow_nan=False),flush=True)
    return report

class AdvantageStrengthComparisonTest(unittest.TestCase):
    def test_controls(self):
        result=main()
        self.assertGreater(result["n_total"],100)
        self.assertEqual(set(result["yearly"]["all"]),{"4","5","6"})
        self.assertGreater(result["coverage"]["2025"]["priced"],50)

if __name__=="__main__":
    unittest.main(verbosity=2)
