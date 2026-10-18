"""Follow-up research: test discovered run-defense+turnover home-underdog cohort.

Home underdog/pick = archived home spread >=0; separate strict underdog >0.
Same-source earlier-week FBS histories, no cross-season leakage. Compare versus
same-spread home sides without the pair and preserve 2026 as untuned holdout.
"""
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit
from test_rundef_turnover_deepdive_2026_10_18 import (
    YEARS,URLS,source,make_year,grade,
)

def split_group(df):
    return {
        "all_home_underdog_and_pickem":grade(df[df.spread.ge(0)]),
        "pair_home_underdog_and_pickem":grade(df[df.spread.ge(0)&df.both.eq(1)]),
        "nonpair_home_underdog_and_pickem":grade(df[df.spread.ge(0)&df.both.eq(0)]),
        "all_strict_home_underdog":grade(df[df.spread.gt(0)]),
        "pair_strict_home_underdog":grade(df[df.spread.gt(0)&df.both.eq(1)]),
        "nonpair_strict_home_underdog":grade(df[df.spread.gt(0)&df.both.eq(0)]),
        "pair_home_pickem":grade(df[df.spread.eq(0)&df.both.eq(1)]),
        "pair_underdog_P4":grade(df[df.spread.gt(0)&df.both.eq(1)&df.group.eq("P4")]),
        "pair_underdog_G6":grade(df[df.spread.gt(0)&df.both.eq(1)&df.group.eq("G6")]),
        "pair_underdog_first7weeks":grade(df[df.spread.gt(0)&df.both.eq(1)&df.week.le(7)]),
        "pair_underdog_weeks8plus":grade(df[df.spread.gt(0)&df.both.eq(1)&df.week.ge(8)]),
        "pair_home_underdog_with3_advantages":grade(df[df.spread.gt(0)&df.both.eq(1)&df.a_count.eq(3)]),
        "pair_home_underdog_with4_advantages":grade(df[df.spread.gt(0)&df.both.eq(1)&df.a_count.eq(4)]),
        "pair_home_underdog_with5_advantages":grade(df[df.spread.gt(0)&df.both.eq(1)&df.a_count.eq(5)]),
    }

def group_strength_match(df):
    # Match compared groups in same season, P4/G6, 0-3.5/4-7.5/8+ dog
    # and Elo gap [-inf,-250), [-250,-100),[-100,0),[0,inf).
    df=df[df.spread.gt(0)&df.result.ne("P")].copy()
    df["line_band"]=pd.cut(df.spread,bins=[0,3.51,7.51,np.inf],labels=False,right=False)
    df["elo_band"]=pd.cut(df.elo_diff,bins=[-np.inf,-250,-100,0,np.inf],labels=False,right=False)
    df["stratum"]=list(zip(df.year,df.group,df.line_band,df.elo_band))
    weighted_num=0.;paired=0;total=int(df.both.sum());cells=[]
    for key,b in df.groupby("stratum"):
        a=b[b.both.eq(1)]
        c=b[b.both.eq(0)]
        if not len(a) or not len(c):continue
        pa=float(a.result.eq("W").mean());pc=float(c.result.eq("W").mean())
        paired+=len(a);weighted_num+=len(a)*(pa-pc)
        cells.append({"stratum":str(key),"n_pair":len(a),"n_control":len(c),
                      "pair_winrate":round(pa,3),"control_winrate":round(pc,3)})
    return {"pair_n":total,"matched_pair_n":paired,
            "stratified_diff_pp":round(100*weighted_num/paired,2) if paired else None,
            "comparison_cells":len(cells),
            "largest_cells":sorted(cells,key=lambda x:x["n_pair"],reverse=True)[:8]}

def validation(train,test):
    # Strict home dogs only; preconfigured controls in addition to all candidates.
    tr=train[train.spread.gt(0)&train.result.ne("P")].copy()
    te=test[test.spread.gt(0)&test.result.ne("P")].copy()
    yy=tr.result.eq("W").to_numpy(dtype=float)
    target=te.result.eq("W").to_numpy(dtype=float)
    def feats(df,extra):
        x=np.column_stack([
            np.ones(len(df)),df.spread.to_numpy(float)/10.,
            df.elo_diff.to_numpy(float)/200.,
            abs(df.elo_diff.to_numpy(float))/200.,
            df.group.eq("P4").to_numpy(dtype=float),
            df.week.to_numpy(float)/10.
        ])
        if extra:x=np.column_stack([x,df.both.to_numpy(float)])
        return x
    models={}
    for extra in [False,True]:
        x=feats(tr,extra);z=feats(te,extra);pen=np.r_[0.,np.full(x.shape[1]-1,6.)]
        def objective(b):
            pred=x@b
            return float(np.logaddexp(0,pred).sum()-yy@pred+0.5*np.sum(pen*b*b))
        def gradient(b):
            return x.T@(expit(x@b)-yy)+pen*b
        fit=minimize(objective,np.zeros(x.shape[1]),jac=gradient,method="BFGS")
        p=expit(z@fit.x)
        m={"Brier":round(float(np.mean((p-target)**2)),5),
           "log_loss":round(float(np.mean(-target*np.log(np.clip(p,1e-6,1))-(1-target)*np.log(np.clip(1-p,1e-6,1)))),5)}
        if extra:
            m["pair_coefficient"]=round(float(fit.x[-1]),4)
            m["pair_odds_ratio"]=round(float(np.exp(fit.x[-1])),3)
        models["with_pair" if extra else "baseline"]=m
    models["n_train"]=len(tr);models["n_test"]=len(te)
    models["ATS_50pct_Brier"]=.25
    models["Brier_delta_pair_vs_baseline"]=round(models["with_pair"]["Brier"]-models["baseline"]["Brier"],5)
    return models

def report():
    with ThreadPoolExecutor(max_workers=9) as pool:
        feeds=dict(pool.map(source,[
            (f"{year}_{kind}",url.format(year=year)) for year in YEARS for kind,url in URLS.items()
        ]))
    frames={y:make_year(y,feeds) for y in YEARS}
    pooled=pd.concat(list(frames.values()),ignore_index=True)
    out={
        "design":"Strict home underdogs distinguish from spread==0; compared to unflagged home underdogs; Elo/line/P4/season matched and prior-year logistic holdouts",
        "annual":{str(y):split_group(frames[y]) for y in YEARS},
        "pooled":split_group(pooled),
        "match":{
            "2024+2025":group_strength_match(pooled[pooled.year.isin((2024,2025))]),
            "all":group_strength_match(pooled)},
        "holdout":{
            "2025":validation(frames[2024],frames[2025]),
            "2026":validation(pd.concat([frames[2024],frames[2025]],ignore_index=True),frames[2026])},
        "caution":"Subgroup discovered retrospectively after spread-band search; small and selection-biased sample; raw -110 ROI hypothetical; 2026 earlier weeks not original frozen selections."}
    print("RUNDEF_TURNOVER_HOME_DOG_REPORT="+json.dumps(out,allow_nan=False),flush=True)
    return out

class RunDefenseTurnoverUnderdogTest(unittest.TestCase):
    def test_research(self):
        r=report()
        self.assertGreater(r["pooled"]["pair_strict_home_underdog"]["n"],40)
        self.assertGreater(r["annual"]["2026"]["pair_strict_home_underdog"]["n"],5)

if __name__=="__main__":
    unittest.main(verbosity=2)
