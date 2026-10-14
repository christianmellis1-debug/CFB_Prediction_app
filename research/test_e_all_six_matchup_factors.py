"""Test E — six prespecified matchup-conditional adjustments to Test C.

Historical development: 2024. Evaluation: 2025 and 2026 Weeks 3–6
(2026 Weeks 5–6 frozen V1.5; early 2026 retrospectively reconstructed).
Research only — NEVER change production V1.5, Test C or six tiers.

Six independent experiment families:
E1 tight bookmaker probability
E2 model vs bookmaker disagreement
E3 weak schedule + exceptional offense
E4 offense vs defense unit imbalance
E5 strong supported venue advantage
E6 sparse FBS-opponent sample reliability

No market threshold is derived from the outcome of the matchup. All
team-relative features use only prior-week team summaries and prior games.
Historical archived opening lines lack independently verified timestamp.
"""
import json, math
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from scipy.special import expit, logit
from scipy.stats import binomtest
import model_v1_5 as model
from matchup_advantages import normalize_fbs_schedule

ROOT=Path(__file__).resolve().parents[1]
HIST=("https://raw.githubusercontent.com/christianmellis1-debug/"
      "CFB_Prediction_app/17a68114f48a4308d1e8312296537d701a65047b/"
      "research/test_c_historical_validation_games.csv")
W26=("https://raw.githubusercontent.com/christianmellis1-debug/"
     "CFB_Prediction_app/research/test-c-head-to-head-weeks3-6-2026-10-13/"
     "research/test_c_head_to_head_weeks3_6_games.csv")
SUM=("https://github.com/sportsdataverse/sportsdataverse-data/releases/"
     "download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_{}.csv")
SCHED=("https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/"
       "schedules/csv/cfb_schedules_{}.csv")
OUT=ROOT/"research/test_e_six_signals_results.json"
GAME=ROOT/"research/test_e_six_signals_games.csv"
BASE_W=0.16927926947215113
COEF=model.CALIBRATION_SLOPE*1.10

def load_cohort():
    h=pd.read_csv(HIST,low_memory=False)
    h=h[h.odds_source.eq("primary_open")].copy()
    assert h.groupby("year").size().to_dict()=={2024:717,2025:720}
    h=h.rename(columns={"id":"game_id","model_home":"v15","market_home":"market"})
    h["home_won"]=h.y.astype(int)
    h=h[["year","week","game_id","game","home_won","v15","market"]]
    h["provenance"]="retrospective_v15_and_archived_open_espnbet"
    y=pd.read_csv(W26,low_memory=False)
    y=y[y.has_open.eq(True)].copy()
    assert y.groupby("week").size().to_dict()=={3:53,4:56,5:56,6:56}
    y=y.rename(columns={"id":"game_id","model_home":"v15","market_home":"market"})
    y["year"]=2026
    y=y[["year","week","game_id","game","home_won","v15","market","prediction_provenance"]]
    y=y.rename(columns={"prediction_provenance":"provenance"})
    c=pd.concat([h,y],ignore_index=True)
    c["game_id"]=pd.to_numeric(c.game_id).astype("int64")
    assert len(c)==1658 and not c.duplicated(["year","game_id"]).any()
    assert c[["market","v15"]].notna().all().all()
    assert c[["market","v15"]].ge(0).all().all() and c[["market","v15"]].le(1).all().all()
    return c

def prior_count(s,week):
    subset=s[(pd.to_numeric(s.week,errors="coerce")<week)&
         s.season_type.astype(str).str.lower().eq("regular")&
         s.completed.astype(str).str.lower().isin(["true","t","1","yes","y"])&
         s.home_points.notna()&s.away_points.notna()&
         s.home_division.astype(str).str.lower().eq("fbs")&
         s.away_division.astype(str).str.lower().eq("fbs")]
    d=Counter()
    for row in subset.itertuples(index=False):
        d[int(row.home_id)]+=1
        d[int(row.away_id)]+=1
    return d

def build_features(c):
    """Exact V1.5 football component reconstruction and strictly prior-game features."""
    datasets={};prev={}
    for year in (2023,2024,2025,2026):
        d=pd.read_csv(SUM.format(year),low_memory=False)
        datasets[year]=d[pd.to_numeric(d.season,errors="coerce").eq(year)].copy()
    for year in (2024,2025,2026):
        sch=normalize_fbs_schedule(pd.read_csv(SCHED.format(year),low_memory=False))
        sch["game_id"]=pd.to_numeric(sch.game_id,errors="coerce").astype("Int64")
        sch["week"]=pd.to_numeric(sch.week,errors="coerce")
        sch["home_points"]=pd.to_numeric(sch.home_points,errors="coerce")
        sch["away_points"]=pd.to_numeric(sch.away_points,errors="coerce")
        sch=sch.dropna(subset=["game_id"]).copy()
        sch["game_id"]=sch.game_id.astype("int64")
        scores,weeks=model.build_weekly_scores(datasets[year])
        profiles=model.build_prior_profiles(datasets[year-1],sch)
        schedules_by_id=sch.set_index("game_id")
        feature_rows=[]
        for wk in sorted(c.loc[c.year.eq(year),"week"].unique()):
            wk=int(wk)
            homes,roads=model._completed_history(sch,wk)
            n_games=prior_count(sch,wk)
            eligible=c[(c.year.eq(year))&c.week.eq(wk)]
            if len(eligible)==0:continue
            cur_weight=model.current_season_weight(wk)
            for observation in eligible.itertuples(index=False):
                gid=int(observation.game_id)
                if gid not in schedules_by_id.index:raise AssertionError(f"Schedule missing {year}:{gid}")
                g=schedules_by_id.loc[gid]
                hi,ai=int(g.home_id),int(g.away_id)
                hs=model._latest_snapshot(scores,weeks,hi,wk)
                aws=model._latest_snapshot(scores,weeks,ai,wk)
                hp,ap=profiles(hi),profiles(ai)
                off_prior=float(hp[0]-ap[0]);def_prior=float(hp[1]-ap[1]);sos_prior=float(hp[2]-ap[2])
                off_cur=float(hs[0]-aws[0]);def_cur=float(hs[1]-aws[1]);sos_cur=float(hs[2]-aws[2])
                off=(1-cur_weight)*off_prior+cur_weight*off_cur
                defense=(1-cur_weight)*def_prior+cur_weight*def_cur
                sos=(1-cur_weight)*sos_prior+cur_weight*sos_cur
                venue=((np.mean(homes[hi]) if homes[hi] else 0)*len(homes[hi])/(len(homes[hi])+3)-
                       (np.mean(roads[ai]) if roads[ai] else 0)*len(roads[ai])/(len(roads[ai])+3))/14.0
                neutral=bool(g.get("neutral_site",False))
                if neutral:venue=0.
                original_score=.35*off+.35*defense+.20*venue+.10*sos
                reconstructed=float(expit(COEF*original_score+model.conference_log_odds(g)))
                # A reconstructed prediction (W3/W4 and historical 2024/2025)
                # must match the stored source exactly, otherwise we might
                # spuriously attribute model-version changes to E.
                pred=float(observation.v15)
                if year<=2025 or wk<=4:
                    if abs(reconstructed-pred)>5e-6:
                        raise AssertionError(f"V1.5 mismatch {year} W{wk} game={gid} {reconstructed} != {pred}")
                # W5-6 2026 remain anchored to originally frozen pregame V1.5.
                prior_home_count=len(homes[hi])
                prior_away_count=len(roads[ai])
                feature_rows.append(dict(year=year,game_id=gid,
                    off=off,defense=defense,sos=sos,venue=venue,
                    offense_abs=float(abs(off)),defense_abs=float(abs(defense)),
                    min_sos=float(min(hs[2],aws[2])),
                    max_off=float(max(hs[0],aws[0])),
                    home_sos=float(hs[2]),away_sos=float(aws[2]),
                    home_off=float(hs[0]),away_off=float(aws[0]),
                    prior_fbs_min=int(min(n_games[hi],n_games[ai])),
                    prior_fbs_max=int(max(n_games[hi],n_games[ai])),
                    home_venue_n=prior_home_count,
                    away_venue_n=prior_away_count,
                    neutral=int(neutral),
                    current_weight=cur_weight,
                    offense_cur_prior_delta=off_cur-off_prior,
                    defense_cur_prior_delta=def_cur-def_prior,
                    sos_cur_prior_delta=sos_cur-sos_prior,
                    reconstruct_v15=reconstructed))
            print("FEATURES",year,"week",wk,"games",len(eligible),flush=True)
        prev[year]=pd.DataFrame(feature_rows)
    rows=pd.concat(list(prev.values()),ignore_index=True)
    assert len(rows)==len(c)
    result=c.merge(rows,on=["year","game_id"],validate="one_to_one")
    assert len(result)==1658
    return result

def candidates():
    families={}
    # E1: in a bookmaker-defined close game, vary market vs V1.5.
    a={}
    for threshold in (.05,.10):
        for weight in (.10,.20,.25,.30,.35,.40):
            a[f"near{int(threshold*100)}pt__v15_{int(weight*100)}"]={
                "trigger":"close","threshold":threshold,"weight":weight}
    families["E1_close_games"]=a

    # E2: opposite probability views, testing greater and lesser influence
    # of the bookmaker with fixed gap thresholds.
    a={}
    for gap in (.05,.10,.15,.20):
        for weight in (.05,.10,.25,.35,.45):
            a[f"gap_{int(gap*100)}pt__v15_{int(weight*100)}"]={
                "trigger":"gap","threshold":gap,"weight":weight}
    families["E2_disagreement"]=a

    # E3: reduce offense's share where a team produced strong offense
    # while facing low-strength past opponents; transfer it to SOS.
    a={}
    for low in (-.50,-.75,-1.0):
        for delta in (.03,.05,.10):
            a[f"weak_sos_{low}__off_to_sos_{int(delta*100)}"]={
                "trigger":"weak_opp","threshold":low,"shift":delta}
    families["E3_opponent_quality"]=a

    # E4: separate offense/defense matchup imbalance from overall model
    # strength, and reward the stronger unit contribution, or counterweight.
    a={}
    for gap in (.25,.50,.75):
        for delta in (.03,.05,.10,-.05):
            a[f"unit_gap_{int(gap*100)}__tilt_{round(delta*100)}"]={
                "trigger":"unit_mismatch","threshold":gap,"shift":delta}
    families["E4_offense_defense_matchups"]=a

    # E5: venue shift only after both teams have actual comparable venue
    # data. Reallocate against offense+defense equally.
    a={}
    for threshold in (.25,.50,.75):
        for samples in (1,2):
            for delta in (-.05,.03,.05,.10):
                a[f"venue_{threshold}__n{samples}__tilt_{round(delta*100)}"]={
                    "trigger":"venue_signal","threshold":threshold,
                    "samples":samples,"shift":delta}
    families["E5_home_road_strength"]=a

    # E6: decrease/increase market dominance in games with little prior
    # FBS experience, or shrink V1.5's current-season share specifically.
    a={}
    for n in (2,3,4,5):
        for weight in (.05,.10,.25,.35):
            a[f"min_fbs_under_{n}__v15_{int(weight*100)}"]={
                "trigger":"data_reliability","threshold":n,"weight":weight}
        for cur_adj in (-.10,-.20):
            a[f"min_fbs_under_{n}__cur_season_{round(cur_adj*100)}"]={
                "trigger":"data_reliability","threshold":n,"cur_shift":cur_adj}
    families["E6_stat_reliability"]=a
    assert sum(len(x) for x in families.values())==101
    return families

def compute(df,spec):
    n=len(df)
    w=np.full(n,BASE_W,dtype=float)
    delta=np.zeros(n,dtype=float)
    event=np.zeros(n,dtype=bool)
    kind=spec["trigger"]
    if kind=="close":
        event=np.abs(df.market.to_numpy(float)-.5)<=spec["threshold"]
    elif kind=="gap":
        event=np.abs(df.v15.to_numpy(float)-df.market.to_numpy(float))>=spec["threshold"]
    elif kind=="weak_opp":
        event=((df.home_sos.to_numpy(float)<=spec["threshold"])&
               (df.home_off.to_numpy(float)>=.5)) | (
               (df.away_sos.to_numpy(float)<=spec["threshold"])&
               (df.away_off.to_numpy(float)>=.5))
        shift=spec["shift"]
        delta[event]=COEF*shift*(df.sos.to_numpy(float)[event]-df.off.to_numpy(float)[event])
    elif kind=="unit_mismatch":
        off=df.off.to_numpy(float)
        defense=df.defense.to_numpy(float)
        diff=np.abs(off)-np.abs(defense)
        event=np.abs(diff)>=spec["threshold"]
        sign=np.sign(diff)
        delta[event]=COEF*spec["shift"]*sign[event]*(off[event]-defense[event])
    elif kind=="venue_signal":
        event=(np.abs(df.venue.to_numpy(float))>=spec["threshold"])&\
             (df.home_venue_n.to_numpy(int)>=spec["samples"])&\
             (df.away_venue_n.to_numpy(int)>=spec["samples"])&\
             (df.neutral.to_numpy(int)==0)
        shift=spec["shift"]
        delta[event]=COEF*shift*(df.venue.to_numpy(float)[event]-
                   .5*df.off.to_numpy(float)[event]-
                   .5*df.defense.to_numpy(float)[event])
    elif kind=="data_reliability":
        event=df.prior_fbs_min.to_numpy(int)<spec["threshold"]
        if "cur_shift" in spec:
            delta[event]=COEF*spec["cur_shift"] * (
                .35*df.offense_cur_prior_delta.to_numpy(float)[event]+
                .35*df.defense_cur_prior_delta.to_numpy(float)[event]+
                .10*df.sos_cur_prior_delta.to_numpy(float)[event])
    else:raise ValueError(kind)
    if "weight" in spec:
        w[event]=spec["weight"]
    model_alt=expit(logit(np.clip(df.v15.to_numpy(float),1e-10,1-1e-10))+delta)
    return w*model_alt+(1-w)*df.market.to_numpy(float),model_alt,event

def assess(y,p,basep):
    if len(y)==0:return None
    p=np.clip(p,1e-12,1-1e-12)
    basep=np.clip(basep,1e-12,1-1e-12)
    correct=(p>=.5)==y
    base_correct=(basep>=.5)==y
    changed=(p>=.5)!=(basep>=.5)
    brier=np.mean((p-y)**2)
    ll=np.mean(-y*np.log(p)-(1-y)*np.log(1-p))
    return {"n":int(len(y)),"wins":int(correct.sum()),
        "losses":int((~correct).sum()),
        "accuracy":round(float(correct.mean()),6),
        "brier":round(float(brier),7),"log_loss":round(float(ll),7),
        "winner_flips":int(changed.sum()),"fixed":int((changed&correct).sum()),
        "broken":int((changed&(~correct)).sum()),
        "net_wins":int(correct.sum()-base_correct.sum()),
        "brier_gain":round(float(np.mean((basep-y)**2)-brier),7)}

def analyze(df):
    fam=candidates()
    y=df.home_won.to_numpy(dtype=int)
    base=BASE_W*df.v15.to_numpy(float)+(1-BASE_W)*df.market.to_numpy(float)
    baseline={}
    for year,subset in [("2024",df.year.eq(2024).to_numpy()),
                        ("2025",df.year.eq(2025).to_numpy()),
                        ("2026",df.year.eq(2026).to_numpy()),
                        ("2026_frozen_w5_6",(df.year.eq(2026)&df.week.ge(5)).to_numpy())]:
        baseline[year]=assess(y[subset],base[subset],base[subset])
    results={};selected={};applied={}
    for family,variants in fam.items():
        scores={}
        for name,spec in variants.items():
            p,m,event=compute(df,spec)
            v={}
            for label,subset in [
                ("development_2024",df.year.eq(2024).to_numpy()),
                ("validation_2025",df.year.eq(2025).to_numpy()),
                ("check_2026",df.year.eq(2026).to_numpy()),
                ("frozen_2026_W5_6",(df.year.eq(2026)&df.week.ge(5)).to_numpy()),
                ("development_2024_triggered",df.year.eq(2024).to_numpy()&event),
                ("validation_2025_triggered",df.year.eq(2025).to_numpy()&event),
                ("check_2026_triggered",df.year.eq(2026).to_numpy()&event),
            ]:
                v[label]=assess(y[subset],p[subset],base[subset])
            # Also show primary model vs odds on affected games.
            v["activation"]={str(year):int(np.sum((df.year.to_numpy(int)==year)&event))
                             for year in (2024,2025,2026)}
            scores[name]=v
        # preregistered selection: 2024 Brier, then fewest changed picks,
        # then lexicographic; *do not look at 2025/2026*.
        win=sorted(scores,key=lambda k:(
            -scores[k]["development_2024"]["brier_gain"],
             scores[k]["development_2024"]["winner_flips"],k))[0]
        selected[family]=win
        results[family]={"selected_by_2024_brier":win,
            "candidates":scores}
        spec=variants[win]
        p,_,event=compute(df,spec)
        applied[family]=dict(pred=p,active=event,spec=spec)
        print("FAMILY",family,"variants",len(variants),"selected",win,
              "2024",scores[win]["development_2024"]["net_wins"],
              "2025",scores[win]["validation_2025"]["net_wins"],
              "2026",scores[win]["check_2026"]["net_wins"],flush=True)
    def ranks(family,period):
        return sorted([
            {"id":k,"wins":v[period]["wins"],"net_wins":v[period]["net_wins"],
             "brier":v[period]["brier"],"brier_gain":v[period]["brier_gain"],
             "active":v["activation"]}
            for k,v in results[family]["candidates"].items()],
            key=lambda x:(-x["net_wins"],-x["brier_gain"],x["id"]))[:8]
    for family in results:
        results[family]["exploratory_best_on_2025"]=ranks(family,"validation_2025")
        results[family]["exploratory_best_on_2026"]=ranks(family,"check_2026")
    # Isolate family per game; no combined optimization until each survives.
    out={
       "experiment":"Test E all six matchup features, 2024 development, 2025 validation, 2026 recent check",
       "created_utc":datetime.now(timezone.utc).isoformat(),
       "weights":dict(model=BASE_W,market=1-BASE_W),
       "n_by_season":{str(y):int(sum(df.year.eq(y))) for y in (2024,2025,2026)},
       "baseline":baseline,"selected_candidates":selected,
       "families":results,
       "methodology":[
          "All candidate thresholds and alternative weights defined in source before calculating historic outcomes.",
          "One candidate per family selected by 2024 Brier. 2025 is a later historical comparison; 2026 is another later check.",
          "2024-25 original V1.5 is current-code retrospective reconstruction, not originally captured live.",
          "2026 Weeks3-4 retrospective V1.5; Weeks5-6 frozen V1.5 with reconstructed component deltas.",
          "2024-25 sportsbook probabilities from archived ESPN BET opening moneylines; 2026 odds from archived DraftKings opening moneylines; quote timestamps not independently verified.",
          "Conditional features use prior-week football metrics or same-game pregame market probabilities; no outcome or final score in eligibility logic.",
          "Some historical weekly advanced summaries may be revised later; earlier experience may include other past games such as FCS matchups.",
          "Market-based probabilities are not independent same-book value betting signals.",
          "Six experiments have 101 candidates in total; historical tuning/multiple-comparison bias makes isolated positive results noncausal.",
          "No deployed Test C probability, V1.5 formula or independent tier selection is changed."
       ]}
    OUT.write_text(json.dumps(out,indent=2,allow_nan=False)+"\n")
    concise=[{"family":fam,"chosen":k,"dev":results[fam]["candidates"][k]["development_2024"],
             "hold":results[fam]["candidates"][k]["validation_2025"],
             "recent":results[fam]["candidates"][k]["check_2026"],
             "frozen":results[fam]["candidates"][k]["frozen_2026_W5_6"],
             "activation":results[fam]["candidates"][k]["activation"],
             "best_2025":results[fam]["exploratory_best_on_2025"][0]}
             for fam,k in selected.items()]
    extra=df[["year","week","game_id","game","home_won","v15","market",
              "off","defense","sos","venue","min_sos","max_off",
              "home_sos","away_sos","home_off","away_off",
              "prior_fbs_min","home_venue_n","away_venue_n",
              "provenance"]].copy()
    extra["testc_baseline"]=base
    for fam,x in applied.items():
        extra[fam+"_pred"]=x["pred"]
        extra[fam+"_active"]=x["active"]
    extra.to_csv(GAME,index=False)
    print("TEST_E_RESULT "+json.dumps({"baseline":baseline,
         "families":concise,"n":len(df)},sort_keys=True),flush=True)

def main():
    c=load_cohort()
    df=build_features(c)
    analyze(df)

if __name__=="__main__":
    main()
