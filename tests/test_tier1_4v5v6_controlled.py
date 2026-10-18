"""Research-only historical 4/6 vs 5/6 vs 6/6 ATS comparison.

"Six" includes the home-field advantage plus 5 statistical advantages.
"Five" = home field plus exactly 4/5 statistical advantages.
"Four" = home field plus exactly 3/5 statistical advantages.

All observations are P4/P4 or G6/G6 FBS games, nonneutral venues,
each using only prior-week box score data. Lines are retrospective archive.
Matched-stratum and holdout tests ask whether 6/6 adds information beyond
market spread, team strength, and conference group.
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

from matchup_advantages import assess, build_advantages

YEARS=(2024,2025,2026)
URLS={
    "schedule":"https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{year}.csv",
    "boxes":"https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_{year}.csv",
    "lines":"https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_betting/betting_{year}.csv",
}
SPREAD_BINS=[-np.inf,-14,-7,0,7,14,np.inf]
SPREAD_NAMES=["home fav 14+","home fav 7-13.5","home fav 0.5-6.5","home dog 0-6.5","home dog 7-13.5","home dog 14+"]
ELO_BINS=[-np.inf,-250,-100,100,250,np.inf]
PENALTY=2.0

def fetch(item):
    key,url=item
    with urlopen(Request(url,headers={"User-Agent":"SaturdayForecast-SixVsControls-2026/1.0"}),timeout=110) as response:
        raw=response.read()
    print("FEED",key,len(raw),flush=True)
    return key,pd.read_csv(BytesIO(raw),low_memory=False)

def truth(column):
    return column.astype(str).str.strip().str.lower().isin(["true","t","1","1.0","yes","y"])

def pct(w,l):
    return round(100*w/(w+l),2) if w+l else None

def wilson(w,n):
    if not n:return [None,None]
    z=1.959963984540054
    p=w/n
    d=1+z*z/n
    center=(p+z*z/(2*n))/d
    rad=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [round(100*(center-rad),2),round(100*(center+rad),2)]

def stats(df):
    n=len(df)
    w=int((df.outcome=="W").sum()) if n else 0
    l=int((df.outcome=="L").sum()) if n else 0
    p=int((df.outcome=="P").sum()) if n else 0
    return {"n":n,"w":w,"l":l,"push":p,"cover_pct":pct(w,l),
            "wilson95_pct":wilson(w,w+l),
            "mean_ATS_margin":round(float(df.ats_margin.mean()),2) if n else None,
            "mean_home_spread":round(float(df.spread.mean()),2) if n else None,
            "mean_elo_diff":round(float(df.elo_diff.mean()),2) if n else None}

def build_year(year,inputs):
    schedule=inputs[f"{year}_schedule"].copy()
    boxes=inputs[f"{year}_boxes"]
    market=inputs[f"{year}_lines"].copy()
    for c in ("game_id","season","week","home_id","away_id","home_points","away_points","home_pregame_elo","away_pregame_elo"):
        schedule[c]=pd.to_numeric(schedule[c],errors="coerce")
    schedule=schedule[
        schedule.season_type.astype(str).str.lower().eq("regular")
        & schedule.home_division.astype(str).str.lower().eq("fbs")
        & schedule.away_division.astype(str).str.lower().eq("fbs")
    ].copy()
    schedule["completed_flag"]=truth(schedule.completed)
    schedule["neutral_flag"]=truth(schedule.neutral_site)
    schedule=schedule.dropna(subset=["week","game_id","home_id","away_id"])
    if schedule.game_id.duplicated().any():raise AssertionError("Duplicate FBS game ID")
    market["game_id"]=pd.to_numeric(market.game_id,errors="coerce")
    market["home_team_spread"]=pd.to_numeric(market.home_team_spread,errors="coerce")
    market=market[truth(market.game_spread_available)&market.game_id.notna()&market.home_team_spread.notna()]
    if "odds_source" in market:
        market=market[~market.odds_source.astype(str).str.lower().eq("default")]
    conflicted=set(market.loc[market.duplicated("game_id",keep=False),"game_id"].astype(int))
    market=market[~market.game_id.isin(conflicted)]
    lines=dict(zip(market.game_id.astype(int),market.home_team_spread.astype(float)))
    rows=[];scope={"in_scope_valid_advantages":0,"in_scope_missing_line":0,"all_final_FBS":int(schedule.completed_flag.sum())}
    for week in sorted(schedule.week.dropna().unique()):
        week=int(week)
        if week<2:continue
        checks=build_advantages(schedule,boxes,week)
        finals=schedule[schedule.week.eq(week)&schedule.completed_flag&~schedule.neutral_flag
                        &schedule.home_points.notna()&schedule.away_points.notna()]
        for _,g in finals.iterrows():
            gid=int(g.game_id)
            a=assess(checks.get(str(gid),{}),"home")
            if a is None:continue
            scope["in_scope_valid_advantages"]+=1
            line=lines.get(gid)
            if line is None:
                scope["in_scope_missing_line"]+=1
                continue
            if pd.isna(g.home_pregame_elo) or pd.isna(g.away_pregame_elo):
                continue
            ats=float(g.home_points-g.away_points+line)
            rows.append({"year":year,"week":week,"game_id":gid,"home":str(g.home_team),
                         "away":str(g.away_team),"group":checks[str(gid)]["group"],
                         "adv":int(a["count"]),"total":int(a["count"])+1,
                         "spread":float(line),"elo_diff":float(g.home_pregame_elo-g.away_pregame_elo),
                         "ats_margin":ats,"outcome":"W" if ats>1e-7 else "L" if ats< -1e-7 else "P"})
    result=pd.DataFrame(rows)
    if result.empty:raise AssertionError(f"No matched historical games for {year}")
    print("BUILT",year,scope,"scored",len(result),"6/6",int(result.total.eq(6).sum()),flush=True)
    return result,scope

def spread_band(df):
    return pd.cut(df.spread,bins=SPREAD_BINS,labels=SPREAD_NAMES,right=False)

def matched(df,target=6,control=5,minimum_control=1):
    # Standardize the comparison group to the actual target mix of
    # spread bucket, pregame Elo bucket, and P4/G6. No fitted propensities.
    z=df[df.total.isin((target,control))&(df.outcome!="P")].copy()
    z["spread_bin"]=pd.cut(z.spread,bins=SPREAD_BINS,labels=False,right=False)
    z["elo_bin"]=pd.cut(z.elo_diff,bins=ELO_BINS,labels=False,right=False)
    z["key"]=list(zip(z.spread_bin,z.elo_bin,z.group))
    diffs=[];used=0;total=int(z.total.eq(target).sum())
    for key,block in z.groupby("key"):
        t=block[block.total.eq(target)]
        c=block[block.total.eq(control)]
        if len(t)<1 or len(c)<minimum_control:continue
        a=float(t.outcome.eq("W").mean());b=float(c.outcome.eq("W").mean())
        diffs.append((len(t),a-b,a,b,len(c)))
        used+=len(t)
    weighted=sum(n*d for n,d,*_ in diffs)/used if used else None
    return {"target":target,"control":control,"target_n":total,"common_support_target_n":used,
            "matched_fraction":round(used/total,3) if total else None,
            "matched_diff_pct_points":round(100*weighted,2) if weighted is not None else None,
            "strata":len(diffs),
            "target_matched_pct":round(100*sum(n*a for n,d,a,b,c in diffs)/used,2) if used else None,
            "control_standardized_pct":round(100*sum(n*b for n,d,a,b,c in diffs)/used,2) if used else None}

def standardized_inputs(train,test,with_counts):
    # Numeric continuous covariates + fixed group flag; 4/6 reference.
    continuous=["spread","elo_diff"]
    tr=train[continuous].to_numpy(float)
    te=test[continuous].to_numpy(float)
    mu=tr.mean(axis=0);sd=tr.std(axis=0);sd[sd<1e-8]=1.
    tr=(tr-mu)/sd;te=(te-mu)/sd
    def add(df,cov):
        pieces=[np.ones((len(df),1)),cov,
                np.abs(df.spread.to_numpy(float)).reshape(-1,1)/14,
                np.abs(df.elo_diff.to_numpy(float)).reshape(-1,1)/250,
                df.group.eq("P4").to_numpy(float).reshape(-1,1)]
        if with_counts:
            pieces.extend([df.total.eq(5).to_numpy(float).reshape(-1,1),
                           df.total.eq(6).to_numpy(float).reshape(-1,1)])
        return np.column_stack(pieces)
    return add(train,tr),add(test,te)

def fit_predict(train,test,counts):
    x,y=standardized_inputs(train,test,counts)
    label=train.outcome.eq("W").to_numpy(float)
    beta0=np.zeros(x.shape[1])
    def fun(b):
        z=x@b
        p=expit(z)
        penalty=PENALTY*np.sum(b[1:]**2)/2
        return float(np.sum(np.logaddexp(0,z)-label*z)+penalty)
    def jac(b):
        p=expit(x@b)
        penalty=np.r_[0.,b[1:]*PENALTY]
        return x.T@(p-label)+penalty
    fit=minimize(fun,beta0,jac=jac,method="BFGS",options={"maxiter":400,"gtol":1e-6})
    if not np.isfinite(fit.x).all():raise RuntimeError("Logistic fit failed to be finite")
    return expit(y@fit.x),fit.x

def score(y,p):
    if not len(y):return None
    p=np.clip(p,1e-6,1-1e-6)
    return {"n":len(y),"brier":round(float(np.mean((p-y)**2)),5),
            "logloss":round(float(np.mean(-y*np.log(p)-(1-y)*np.log(1-p))),5)}

def holdout(train,test):
    train=train[(train.total.isin([4,5,6]))&(train.outcome!="P")]
    test=test[(test.total.isin([4,5,6]))&(test.outcome!="P")].copy()
    y=test.outcome.eq("W").to_numpy(float)
    p0,b0=fit_predict(train,test,False)
    p1,b1=fit_predict(train,test,True)
    out={"training_games":len(train),"tested_games":len(test),
         "market_half":score(y,np.full(len(y),.5)),
         "baseline_covariates":score(y,p0),
         "with_advantage_counts":score(y,p1),
         "delta_brier_with_counts_minus_without":round(float(np.mean((p1-y)**2-(p0-y)**2)),5),
         "trained_odds_ratio_5_vs_4":round(float(np.exp(b1[-2])),3),
         "trained_odds_ratio_6_vs_4":round(float(np.exp(b1[-1])),3),
         "trained_odds_ratio_6_vs_5":round(float(np.exp(b1[-1]-b1[-2])),3)}
    for level in (4,5,6):
        subset=test.total.eq(level).to_numpy()
        out[f"level_{level}"]={"n":int(subset.sum()),
               "baseline":score(y[subset],p0[subset]),
               "with_counts":score(y[subset],p1[subset])}
    return out

def run():
    with ThreadPoolExecutor(max_workers=9) as pool:
        feeds=dict(pool.map(fetch,[(f"{y}_{kind}",template.format(year=y))
                                   for y in YEARS for kind,template in URLS.items()]))
    frames=[];coverage={}
    for year in YEARS:
        frame,cov=build_year(year,feeds)
        frames.append(frame);coverage[year]=cov
    all_data=pd.concat(frames,ignore_index=True)
    eligible=all_data[all_data.total.isin((4,5,6))].copy()
    outcome={"definition":"Total includes home field: 4/6=3/5 statistical advantages, 5/6=4/5, 6/6=5/5",
       "historical_caveat":"Retrospective ESPN-derived lines and recalculated pregame-week statistical qualifiers, not frozen original bets",
       "coverage":coverage,"yearly":{},"pooled":{},
       "matched_comparison":{},"holdout":{}}
    for yr in YEARS:
        part=eligible[eligible.year.eq(yr)]
        outcome["yearly"][str(yr)]={str(k):stats(part[part.total.eq(k)]) for k in (4,5,6)}
        outcome["yearly"][str(yr)]["by_spread"]={
            str(k):{str(bin_name):stats(part[part.total.eq(k)&spread_band(part).eq(bin_name)])
                   for bin_name in SPREAD_NAMES} for k in (4,5,6)}
    outcome["pooled"]={str(k):stats(eligible[eligible.total.eq(k)]) for k in (4,5,6)}
    for label,ds in (("2024+2025",eligible[eligible.year.isin((2024,2025))]),
                     ("2026",eligible[eligible.year.eq(2026)]),
                     ("2024-2026",eligible)):
        outcome["matched_comparison"][label]={
            "6_vs_5":matched(ds,6,5),
            "6_vs_4":matched(ds,6,4)}
    outcome["holdout"]["2025_trained_2024"]=holdout(
        eligible[eligible.year.eq(2024)],eligible[eligible.year.eq(2025)])
    outcome["holdout"]["2026_trained_2024_2025"]=holdout(
        eligible[eligible.year.isin((2024,2025))],eligible[eligible.year.eq(2026)])
    # Supplemental simple differences on full available samples; this is not a
    # causal estimate and fails to adjust for non-overlapping matchup strata.
    outcome["pooled_raw_differences_pp"]={
        "6_minus_5":round(outcome["pooled"]["6"]["cover_pct"]-outcome["pooled"]["5"]["cover_pct"],2),
        "6_minus_4":round(outcome["pooled"]["6"]["cover_pct"]-outcome["pooled"]["4"]["cover_pct"],2)}
    print("ADVANTAGES_4_5_6_CONTROLLED_REPORT="+json.dumps(outcome,allow_nan=False),flush=True)
    return outcome

class CompareAdvantageLevels(unittest.TestCase):
    def test_historical_controlled_comparison(self):
        report=run()
        for y in YEARS:
            self.assertGreater(report["yearly"][str(y)]["6"]["n"],10)
            self.assertGreater(report["yearly"][str(y)]["5"]["n"],10)
            self.assertGreater(report["yearly"][str(y)]["4"]["n"],10)

if __name__=="__main__":
    unittest.main(verbosity=2)
