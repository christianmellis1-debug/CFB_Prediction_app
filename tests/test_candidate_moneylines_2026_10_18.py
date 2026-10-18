"""Historical moneyline profitability audit: run defense + turnover advantages.

Uses pregame week-only FBS matchup characteristics from prior research.
Historical ESPN BET moneylines (2024/25) and DraftKings ESPN pickcenter
(2026) sourced from publicly archived game JSON; prices are not proven
time-stamped pregame quotes. Missing or noncomparable odds exclude a game.
Never infer ML odds from spreads. Outcomes are straight-up home wins.
"""
import json
import statistics
import unittest
import numpy as np
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from test_rundef_turnover_deepdive_2026_10_18 import YEARS,URLS,source,make_year

ODDS_ROOT="https://raw.githubusercontent.com/sportsdataverse/cfbfastR-cfb-raw/main/cfb/betting/json/{}.json"
RESEARCH_BETS=("pair_all","pair_home_dog","pair_three_of_five","pair_three_of_five_home_dog","pair_five_of_five")

def implied(ml):
    return -ml/(100.-ml) if ml<0 else 100./(ml+100.)

def unit_profit(ml):
    return ml/100. if ml>0 else 100./abs(ml)

def norm_price(v):
    if isinstance(v,dict):
        v=v.get("american") or v.get("alternateDisplayValue")
    try:
        s=str(v).strip().replace("+","").replace(",","")
        p=float(s)
        if not np.isfinite(p) or -100<p<100 or p==0 or abs(p)>100000:
            return None
        return p
    except (ValueError,TypeError):return None

def unpack(raw,year):
    picks=raw.get("pickcenter",[])
    full=(raw.get("odds_full") or {}).get("items") or []
    all_options=list(picks)+list(full)
    pref="DraftKings" if year==2026 else "ESPN BET"
    for item in all_options:
        provider=(item.get("provider") or {}).get("name","")
        if provider!=pref:continue
        home=item.get("homeTeamOdds") or {}
        away=item.get("awayTeamOdds") or {}
        hp=norm_price(home.get("moneyLine"))
        ap=norm_price(away.get("moneyLine"))
        if hp is None:
            hp=norm_price((home.get("close") or {}).get("moneyLine"))
        if ap is None:
            ap=norm_price((away.get("close") or {}).get("moneyLine"))
        if hp is None or ap is None:continue
        home_implied,away_implied=implied(hp),implied(ap)
        overround=home_implied+away_implied
        if not 0.99<=overround<=1.35:
            continue
        return {"home_ml":hp,"away_ml":ap,"provider":provider,
                "fair_p":home_implied/overround,"book_p":home_implied,
                "overround":overround}
    return None

def get_odds(row):
    gid=int(row["game_id"]);year=int(row["year"])
    try:
        with urlopen(Request(ODDS_ROOT.format(gid),headers={"User-Agent":"SaturdayForecast-MLResearch/1.0"}),timeout=30) as r:
            data=json.load(r)
    except (HTTPError,TimeoutError,ValueError,Exception) as exc:
        # Missing games or provider are legitimate coverage gaps.
        return {"game_id":gid,"error":str(exc)[:85],"odds":None}
    return {"game_id":gid,"error":None,"odds":unpack(data,year)}

def count(frame):
    n=len(frame)
    w=int(frame.su_win.sum()) if n else 0
    return {"n":int(n),"W":w,"L":n-w,"SU_pct":round(100*w/n,2) if n else None,
            "mean_home_spread":round(float(frame.spread.mean()),2) if n else None}

def grade(frame):
    frame=frame.copy()
    base=count(frame)
    priced=frame[frame.home_ml.notna()]
    base.update({"odds_coverage":int(len(priced)),
                 "odds_coverage_pct":round(100*len(priced)/len(frame),1) if len(frame) else None})
    if priced.empty:return base
    profit=np.where(priced.su_win.to_numpy(bool),
                    np.where(priced.home_ml.to_numpy(float)>0,
                             priced.home_ml.to_numpy(float)/100,
                             100/abs(priced.home_ml.to_numpy(float))),-1.)
    sample=int(len(priced))
    base.update({
        "priced_W":int(priced.su_win.sum()),
        "priced_L":int((~priced.su_win).sum()),
        "priced_SU_pct":round(100*priced.su_win.mean(),2),
        "odds_provider":{str(k):int(v) for k,v in priced.provider.value_counts().items()},
        "average_american_odds":round(float(priced.home_ml.mean()),1),
        "median_american_odds":round(float(priced.home_ml.median()),1),
        "mean_implied_market_probability_pct":round(float(100*priced.book_p.mean()),2),
        "mean_no_vig_home_probability_pct":round(float(100*priced.fair_p.mean()),2),
        "actual_W_minus_expected_no_vig":round(float(priced.su_win.sum()-priced.fair_p.sum()),2),
        "profit_10_stake_USD":round(float(10*profit.sum()),2),
        "roi_pct":round(float(100*profit.mean()),2),
        "win_odds_examples":sorted(float(x) for x in priced.home_ml.unique())[:5],
        "provider_warning":"archived ESPN-derived prices, snapshot timing not independently validated"
    })
    return base

def cohorts(frame):
    return {
        "pair_all":frame.both.eq(1),
        "pair_home_dog":frame.both.eq(1)&frame.spread.gt(0),
        "pair_favorites":frame.both.eq(1)&frame.spread.lt(0),
        "pair_three_of_five":frame.both.eq(1)&frame.a_count.eq(3),
        "pair_three_of_five_home_dog":frame.both.eq(1)&frame.a_count.eq(3)&frame.spread.gt(0),
        "pair_four_of_five":frame.both.eq(1)&frame.a_count.eq(4),
        "pair_five_of_five":frame.both.eq(1)&frame.a_count.eq(5),
        "pair_home_dog_P4":frame.both.eq(1)&frame.spread.gt(0)&frame.group.eq("P4"),
        "pair_home_dog_G6":frame.both.eq(1)&frame.spread.gt(0)&frame.group.eq("G6"),
        "pair_home_dog_spread_0to3_5":frame.both.eq(1)&frame.spread.gt(0)&frame.spread.le(3.5),
        "pair_home_dog_spread_4to7_5":frame.both.eq(1)&frame.spread.gt(3.5)&frame.spread.le(7.5),
        "pair_home_dog_spread_8plus":frame.both.eq(1)&frame.spread.gt(7.5),
        "pair_favorite_moderate":frame.both.eq(1)&frame.spread.ge(-13.5)&frame.spread.le(-7),
        "pair_favorite_heavy":frame.both.eq(1)&frame.spread.le(-14),
        "pair_favorite_light":frame.both.eq(1)&frame.spread.gt(-7)&frame.spread.lt(0),
        "pair_home_dog_weeks3to7":frame.both.eq(1)&frame.spread.gt(0)&frame.week.between(3,7),
    }

def run():
    with ThreadPoolExecutor(max_workers=9) as pool:
        feeds=dict(pool.map(source,[(f"{y}_{k}",tpl.format(year=y)) for y in YEARS for k,tpl in URLS.items()]))
    dfs={y:make_year(y,feeds) for y in YEARS}
    frame=pd.concat([dfs[y] for y in YEARS],ignore_index=True)
    frame["su_win"]=frame.home_margin.gt(0)
    pair=frame[frame.both.eq(1)].copy()
    tasks=pair[["game_id","year"]].to_dict("records")
    print("FETCH_ML_CANDIDATES",len(tasks),flush=True)
    odds={};errors={}
    with ThreadPoolExecutor(max_workers=20) as pool:
        jobs=[pool.submit(get_odds,task) for task in tasks]
        for idx,future in enumerate(as_completed(jobs)):
            result=future.result()
            odds[result["game_id"]]=result["odds"]
            if result["error"]:
                errors[result["game_id"]]=result["error"]
            if (idx+1)%100==0:print("ODDS_FETCH_PROGRESS",idx+1,len(tasks),flush=True)
    priced=pair.copy()
    for key in ("home_ml","away_ml","provider","fair_p","book_p","overround"):
        priced[key]=priced.game_id.map(lambda k:(odds.get(int(k)) or {}).get(key))
    frame=frame.merge(priced[["game_id","home_ml","away_ml","provider","fair_p","book_p","overround"]],
                      on="game_id",how="left",validate="one_to_one")
    print("MONEYLINE_PROVIDERS",priced.provider.value_counts(dropna=False).to_dict(),flush=True)
    report={
      "data_warning":"Moneyline quotes from ESPN-derived archived game odds JSON; prices could be later snapshots, market availability is incomplete and not verified as pregame. Never impute lines from spreads.",
      "n_odds_attempted":len(tasks),"n_network_fail":len(errors),
      "network_error_sample":[{"game_id":int(k),"error":v} for k,v in list(errors.items())[:6]],
      "annual":{},
      "all_years":{},
      "by_group":{},
      "candidate_dog_game_examples":[],
    }
    for y in YEARS:
        current=frame[frame.year.eq(y)]
        report["annual"][str(y)]={name:grade(current[mask]) for name,mask in cohorts(current).items()}
    for label,df in [("all",frame),("2024_2025",frame[frame.year.isin((2024,2025))])]:
        report["all_years"][label]={name:grade(df[mask]) for name,mask in cohorts(df).items()}
    report["candidate_dog_game_examples"]=[
        {"season":int(x.year),"week":int(x.week),"home":x.home,"away":x.away,
         "spread":float(x.spread),"moneyline":float(x.home_ml) if pd.notna(x.home_ml) else None,
         "provider":x.provider if pd.notna(x.provider) else None,
         "SU_win":bool(x.su_win),"outcome_margin":float(x.home_margin)}
        for _,x in frame[frame.both.eq(1)&frame.spread.gt(0)].sort_values(["year","week"]).iterrows()
    ]
    print("RUNDOG_MONEYLINE_REPORT="+json.dumps(report,allow_nan=False,default=lambda x:x.item() if isinstance(x,np.generic) else str(x)),flush=True)
    return report

class CandidateMoneylineHistorical(unittest.TestCase):
    def test_historical_prices_and_outright(self):
        report=run()
        self.assertEqual(report["all_years"]["all"]["pair_all"]["n"],402)
        self.assertEqual(report["all_years"]["all"]["pair_home_dog"]["n"],58)
        self.assertGreater(report["all_years"]["all"]["pair_home_dog"]["odds_coverage"],10)

if __name__=="__main__":unittest.main(verbosity=2)
