"""Research only: Run-defense + turnover margin pair ATS deep dive.

Immutable definitions for holdouts:
* Individual home-side pair: prior-week defensive rushing YPC allowed lower
  than opponent's, and takeaways-minus-giveaways per game higher.
* Magnitudes are raw pregame differences, not future data.
* Historical 2024-only cutoffs -> 2025; 2024–25 cutoffs -> 2026.
* An Elo margin forecast fit on earlier season(s) -> later year.
* At assumed -110 with flat $10 stakes, winners profit $9.0909, losers
  lose $10; no actual price histories are asserted.
"""
import json
import unittest
import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.optimize import minimize
from concurrent.futures import ThreadPoolExecutor
from itertools import product

from test_tier1_individual_combinations_2026_10_18 import (
    YEARS, URLS, source, yes, summarize,
)
from matchup_advantages import build_advantages, assess

SPREAD_BUCKETS=[(-float("inf"),-14,"Fav -14+"),(-14,-7,"Fav -7 to -13.5"),(-7,0,"Fav -0.5 to -6.5"),(0,float("inf"),"Home dog/pick")]
EPS=1e-8

def make_year(year, feeds):
    schedule=feeds[f"{year}_schedule"].copy()
    boxes=feeds[f"{year}_boxes"]
    market=feeds[f"{year}_market"].copy()
    for c in ("game_id","week","home_id","away_id","home_points","away_points","home_pregame_elo","away_pregame_elo"):
        schedule[c]=pd.to_numeric(schedule[c],errors="coerce")
    schedule=schedule[schedule.season_type.astype(str).str.lower().eq("regular")
                      & schedule.home_division.astype(str).str.lower().eq("fbs")
                      & schedule.away_division.astype(str).str.lower().eq("fbs")].copy()
    schedule["finished"]=yes(schedule.completed)
    schedule["neutral"]=yes(schedule.neutral_site)
    schedule=schedule.dropna(subset=["game_id","week","home_id","away_id"])
    if schedule.game_id.duplicated().any():raise ValueError("Duplicate schedule ID")
    market["game_id"]=pd.to_numeric(market.game_id,errors="coerce")
    market["home_team_spread"]=pd.to_numeric(market.home_team_spread,errors="coerce")
    market=market[yes(market.game_spread_available)&market.game_id.notna()&market.home_team_spread.notna()]
    if "odds_source" in market:
        market=market[~market.odds_source.astype(str).str.lower().eq("default")]
    if market.game_id.duplicated().any():
        market=market[~market.game_id.isin(market.loc[market.game_id.duplicated(False),"game_id"])]
    lines=dict(zip(market.game_id.astype(int),market.home_team_spread.astype(float)))
    rows=[]
    for week in sorted(schedule.week.dropna().astype(int).unique()):
        if week<2:continue
        adv=build_advantages(schedule,boxes,week)
        gset=schedule[schedule.week.eq(week)&schedule.finished&~schedule.neutral
                      &schedule.home_points.notna()&schedule.away_points.notna()]
        for _,g in gset.iterrows():
            gid=int(g.game_id);rec=adv.get(str(gid),{})
            a=assess(rec,"home")
            if a is None or gid not in lines:continue
            if pd.isna(g.home_pregame_elo) or pd.isna(g.away_pregame_elo):continue
            spread=lines[gid];actual_margin=float(g.home_points-g.away_points)
            cover=actual_margin+spread
            def_edge=float(rec["away"][2]-rec["home"][2])
            to_edge=float(rec["home"][4]-rec["away"][4])
            rows.append({
                "year":year,"week":week,"game_id":gid,"home":str(g.home_team),"away":str(g.away_team),
                "group":rec["group"],"spread":spread,"elo_diff":float(g.home_pregame_elo-g.away_pregame_elo),
                "home_margin":actual_margin,"ats_margin":cover,
                "result":"W" if cover>EPS else "L" if cover< -EPS else "P",
                "a_count":int(a["count"]),
                "def_edge":def_edge,"to_edge":to_edge,
                "run_def":int(a["outcomes"][2]=="Advantage"),
                "turnover":int(a["outcomes"][4]=="Advantage"),
                "both":int(a["outcomes"][2]=="Advantage" and a["outcomes"][4]=="Advantage"),
            })
    result=pd.DataFrame(rows)
    assert not result.empty
    print("MAKE",year,"all",len(result),"both",int(result.both.sum()),flush=True)
    return result

def grade(frame):
    w=int(frame.result.eq("W").sum())
    l=int(frame.result.eq("L").sum())
    p=int(frame.result.eq("P").sum())
    n=w+l
    gross=9.090909090909092*w-10*l
    return {"n":int(len(frame)),"W":w,"L":l,"P":p,
            "ATS_pct":round(100*w/n,2) if n else None,
            "roi_-110_flat10_pct":round(100*gross/(10*n),2) if n else None,
            "hypothetical_profit_flat10_usd":round(gross,2),
            "avg_home_spread":round(float(frame.spread.mean()),2) if len(frame) else None,
            "avg_elo_diff":round(float(frame.elo_diff.mean()),1) if len(frame) else None}

def group_analysis(df):
    candidate=df[df.both.eq(1)]
    other=df[df.both.eq(0)]
    d={
        "all":grade(df),"pair_yes":grade(candidate),"pair_no":grade(other),
        "by_group":{g:grade(candidate[candidate.group.eq(g)]) for g in ("P4","G6")},
        "by_spread":{label:grade(candidate[candidate.spread.ge(lo)&candidate.spread.lt(hi)])
                     for lo,hi,label in SPREAD_BUCKETS},
        "by_additional_advantages":{str(n):grade(candidate[candidate.a_count.eq(n)])
                                      for n in range(2,6)},
        "by_week":{str(int(week)):grade(candidate[candidate.week.eq(week)])
                   for week in sorted(df.week.unique())},
    }
    return d

def median_filter(training,eval_):
    train=training[training.both.eq(1)]
    test=eval_[eval_.both.eq(1)].copy()
    cut_run=float(train.def_edge.median())
    cut_to=float(train.to_edge.median())
    test["run_high"]=test.def_edge.ge(cut_run)
    test["to_high"]=test.to_edge.ge(cut_to)
    return {
        "train_candidate_n":len(train),"median_run_edge_YPC":round(cut_run,3),
        "median_turnover_edge_per_game":round(cut_to,3),
        "test_all_pair":grade(test),
        "both_above_medians":grade(test[test.run_high&test.to_high]),
        "either_above_median":grade(test[test.run_high|test.to_high]),
        "run_only_high":grade(test[test.run_high&~test.to_high]),
        "to_only_high":grade(test[~test.run_high&test.to_high]),
        "both_below_medians":grade(test[~test.run_high&~test.to_high]),
        "above_run_median":grade(test[test.run_high]),
        "above_turnover_median":grade(test[test.to_high]),
    }

def fit_margin(prepared):
    # Pre-registered linear-Elo margin benchmark with nonneutral same-group
    # game outcomes. No game from evaluation season participates in fitting.
    X=np.column_stack([np.ones(len(prepared)),prepared.elo_diff.to_numpy(float)])
    y=prepared.home_margin.to_numpy(float)
    return np.linalg.lstsq(X,y,rcond=None)[0]

def test_margin(train, test):
    beta=fit_margin(train)
    work=test.copy()
    work["predicted_margin"]=beta[0]+beta[1]*work.elo_diff
    work["edge"]=work.predicted_margin+work.spread
    pair=work[work.both.eq(1)]
    return {
        "fitted_intercept":round(float(beta[0]),4),
        "fitted_elo_coefficient":round(float(beta[1]),6),
        "all_with_spread_value":grade(work[work.edge.gt(0)]),
        "candidate_all":grade(pair),
        "candidate_elo_positive":grade(pair[pair.edge.gt(0)]),
        "candidate_elo_atleast_2":grade(pair[pair.edge.ge(2)]),
        "candidate_elo_atleast_3":grade(pair[pair.edge.ge(3)]),
        "candidate_elo_negative":grade(pair[pair.edge.le(0)]),
        "candidate_elo_positive_by_group":{
            g:grade(pair[pair.group.eq(g)&pair.edge.gt(0)]) for g in ("P4","G6")
        },
        "candidate_elo_positive_by_spread":{
            label:grade(pair[pair.spread.ge(lo)&pair.spread.lt(hi)&pair.edge.gt(0)])
            for lo,hi,label in SPREAD_BUCKETS
        },
    }

def adjusted_regression(train,test):
    """Estimate incremental information of pair flag against existing line/Elo.

    Standardize via predetermined scaling, regularized logistic. Strictly
    out-of-year; no chosen feature bins from evaluation year.
    """
    train=train[train.result.ne("P")]
    test=test[test.result.ne("P")]
    def feats(df,extra):
        s=df.spread.to_numpy(float)
        e=df.elo_diff.to_numpy(float)
        x=[np.ones(len(df)),s/10,np.abs(s)/10,e/200,np.abs(e)/200,
           df.week.to_numpy(float)/10,df.group.eq("P4").to_numpy(float)]
        if extra:x.extend([df.run_def.to_numpy(float),df.turnover.to_numpy(float),
                            df.both.to_numpy(float)])
        return np.column_stack(x)
    y=train.result.eq("W").to_numpy(float)
    test_y=test.result.eq("W").to_numpy(float)
    out={}
    for extra in (False,True):
        a=feats(train,extra);b=feats(test,extra)
        reg=np.r_[0.,np.full(a.shape[1]-1,8.)]
        def objective(beta):
            q=a@beta
            return float(np.logaddexp(0,q).sum()-y@q+0.5*np.sum(reg*beta**2))
        def gradient(beta):
            return a.T@(expit(a@beta)-y)+reg*beta
        fit=minimize(objective,np.zeros(a.shape[1]),jac=gradient,method="BFGS")
        prob=expit(b@fit.x)
        result={"Brier":round(float(np.mean((prob-test_y)**2)),6),
                "log_loss":round(float(np.mean(-test_y*np.log(np.clip(prob,1e-6,1-1e-6))-(1-test_y)*np.log(np.clip(1-prob,1e-6,1-1e-6)))),6)}
        if extra:result["pair_interaction_coefficient"]=round(float(fit.x[-1]),4)
        out["plus_pair" if extra else "control"]=result
    out["baseline_market_50_Brier"]=.25
    out["delta_Brier_plus_pair_minus_control"]=round(out["plus_pair"]["Brier"]-out["control"]["Brier"],6)
    return out

def main():
    with ThreadPoolExecutor(max_workers=9) as pool:
        feeds=dict(pool.map(source,[
            (f"{year}_{kind}",url.format(year=year)) for year in YEARS for kind,url in URLS.items()
        ]))
    frames={year:make_year(year,feeds) for year in YEARS}
    pre2026=pd.concat([frames[2024],frames[2025]],ignore_index=True)
    overall=pd.concat(list(frames.values()),ignore_index=True)
    out={
        "definition":"Home pregame rushing YPC allowed better than away + home turnover margin per game greater than away",
        "caution":"Archived ESPN spreads not original frozen prices. All home-side research observations; not production tier selections. ROI assumes -110 uniformly and ignores line availability/slippage/fees.",
        "annual":{str(year):group_analysis(frames[year]) for year in YEARS},
        "pooled":group_analysis(overall),
        "holdout":{},
    }
    for year,training in [(2025,frames[2024]),(2026,pre2026)]:
        test=frames[year]
        out["holdout"][str(year)]={
            "magnitude_median":median_filter(training,test),
            "Elo_spread_value":test_margin(training,test),
            "pair_incremental_vs_market_strength":adjusted_regression(training,test),
        }
    # Explicit 2026 retrospective diagnostic: compare advantage count > etc
    # with fixed 2024+25 medians, and isolate Week 7 locked Tier1 intersection.
    out["2026_week7_pair"]={
        "pair":grade(frames[2026][frames[2026].week.eq(7)&frames[2026].both.eq(1)]),
        "pair_sixof6":grade(frames[2026][frames[2026].week.eq(7)&frames[2026].both.eq(1)&frames[2026].a_count.eq(5)])
    }
    print("RUNDEF_TURNOVER_DEEP_DIVE_REPORT="+json.dumps(out,allow_nan=False),flush=True)
    return out

class RunDefenseTurnoverTest(unittest.TestCase):
    def test_research(self):
        out=main()
        self.assertGreater(out["pooled"]["pair_yes"]["n"],350)
        self.assertGreater(out["annual"]["2026"]["pair_yes"]["n"],40)
        self.assertEqual(out["holdout"]["2026"]["Elo_spread_value"]["candidate_all"]["W"],37)

if __name__=="__main__":
    unittest.main(verbosity=2)
