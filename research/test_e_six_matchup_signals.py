"""Six conditional football-matchup hypotheses: train 2024; validate 2025 and 2026 W3–6.

PROVENANCE: Historical V1.5 is retrospective (2024/2025, 2026 W3/W4),
2026 W5/W6 is frozen archived V1.5, but conditional candidate offsets are
retrospectively reconstructed. Historical ESPN BET open and 2026 DraftKings
open are *archived quotes* with unverified first-publication timestamps.
This is research only; do not mutate app, tiers, live V1.5 or Test C.
"""
import json, math
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from scipy.special import expit, logit
from scipy.stats import binomtest
import model_v1_5 as m
from matchup_advantages import normalize_fbs_schedule

ROOT=Path(__file__).resolve().parents[1]
SUMMARY="https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_{}.csv"
SCHEDULE="https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{}.csv"
HIST="https://raw.githubusercontent.com/christianmellis1-debug/CFB_Prediction_app/17a68114f48a4308d1e8312296537d701a65047b/research/test_c_historical_validation_games.csv"
CURRENT="https://raw.githubusercontent.com/christianmellis1-debug/CFB_Prediction_app/research/test-c-head-to-head-weeks3-6-2026-10-13/research/test_c_head_to_head_weeks3_6_games.csv"
WEIGHT=.16927926947215113
K=m.CALIBRATION_SLOPE*1.10
OUT=ROOT/"research/test_e_six_matchup_results.json"
GAMES=ROOT/"research/test_e_six_matchup_games.csv"

def prepare():
    hist=pd.read_csv(HIST,low_memory=False)
    hist=hist[hist.odds_source.eq("primary_open")]
    z=hist[["year","week","id","game","y","model_home","market_home"]].copy()
    now=pd.read_csv(CURRENT,low_memory=False)
    now=now[now.has_open.eq(True)]
    z26=pd.DataFrame({
      "year":2026,"week":now.week,"id":now.id,"game":now.game,
      "y":now.home_won,"model_home":now.model_home,"market_home":now.market_home,
    })
    data=pd.concat([z,z26],ignore_index=True)
    data["id"]=pd.to_numeric(data.id).astype("int64")
    assert not data.duplicated(["year","id"]).any()
    assert data.groupby("year").size().to_dict()=={2024:717,2025:720,2026:221}
    assert data.model_home.between(.00001,.99999).all()
    assert data.market_home.between(.00001,.99999).all()
    data["base_testc"]=WEIGHT*data.model_home+(1-WEIGHT)*data.market_home
    return data

def features(data):
    features=[]
    for yr in [2024,2025,2026]:
        schedule=normalize_fbs_schedule(pd.read_csv(SCHEDULE.format(yr),low_memory=False))
        sum_now=pd.read_csv(SUMMARY.format(yr),low_memory=False)
        sum_prior=pd.read_csv(SUMMARY.format(yr-1),low_memory=False)
        scores,weeks=m.build_weekly_scores(sum_now)
        prior=m.build_prior_profiles(sum_prior,schedule)
        schedule["game_id"]=pd.to_numeric(schedule.game_id,errors="coerce").astype("Int64")
        schedule=schedule.dropna(subset=["game_id"])
        by_id={int(r.game_id):r for _,r in schedule.iterrows()}
        sub=data[data.year.eq(yr)]
        for week in sorted(sub.week.astype(int).unique()):
            home_hist,road_hist=m._completed_history(schedule,week)
            past=schedule[(pd.to_numeric(schedule.week,errors="coerce")<week)&
               schedule.completed.astype(str).str.lower().isin(["true","t","1","yes","y"])&
               schedule.season_type.astype(str).str.lower().eq("regular")&
               schedule.home_points.notna()&schedule.away_points.notna()]
            n_games=defaultdict(int)
            for _,r in past.iterrows():
                n_games[int(r.home_id)]+=1;n_games[int(r.away_id)]+=1
            cur=m.current_season_weight(week)
            for row in sub[sub.week.eq(week)].itertuples(index=False):
                if int(row.id) not in by_id:raise ValueError(f"Missing schedule game {yr} {row.id}")
                g=by_id[int(row.id)];h,a=int(g.home_id),int(g.away_id)
                hs=m._latest_snapshot(scores,weeks,h,week);az=m._latest_snapshot(scores,weeks,a,week)
                hp=prior(h);ap=prior(a)
                offcur=hs[0]-az[0];defcur=hs[1]-az[1];soscur=hs[2]-az[2]
                offpr=hp[0]-ap[0];defpr=hp[1]-ap[1];sospr=hp[2]-ap[2]
                off=(1-cur)*offpr+cur*offcur
                de=(1-cur)*defpr+cur*defcur
                sos=(1-cur)*sospr+cur*soscur
                nh,na=len(home_hist[h]),len(road_hist[a])
                venue=((np.mean(home_hist[h]) if nh else 0)*nh/(nh+3)-
                       (np.mean(road_hist[a]) if na else 0)*na/(na+3))/14.
                if bool(g.get("neutral_site",False)):venue=0.
                features.append({
                    "year":yr,"id":int(row.id),
                    "offdiff":off,"defdiff":de,"sosdiff":sos,"venue":venue,
                    "offcur_minus_prior":offcur-offpr,
                    "defcur_minus_prior":defcur-defpr,
                    "soscur_minus_prior":soscur-sospr,
                    "min_prior_fbs":min(n_games[h],n_games[a]),
                    "n_home_venue":nh,"n_away_venue":na,
                    "neutral":bool(g.get("neutral_site",False)),
                })
            print("PREPARED_FEATURES",yr,week,len(sub[sub.week.eq(week)]),flush=True)
    feat=pd.DataFrame(features)
    joined=data.merge(feat,on=["year","id"],validate="one_to_one")
    assert len(joined)==len(data)
    return joined

def metrics(df,p):
    if len(df)==0:return None
    y=df.y.to_numpy(int)
    p=np.clip(np.asarray(p,dtype=float),1e-12,1-1e-12)
    good=(p>=.5)==y
    return dict(n=len(y),wins=int(good.sum()),losses=int((~good).sum()),
                accuracy=round(float(good.mean()),6),
                brier=round(float(np.mean((p-y)**2)),7),
                log_loss=round(float(np.mean(-y*np.log(p)-(1-y)*np.log(1-p))),7))

def variants():
    out=[]
    add=lambda family,name,kind,condition,threshold,intensity:out.append({
      "family":family,"name":name,"kind":kind,"condition":condition,
      "threshold":threshold,"intensity":intensity})
    # E1: market home probability close to 50%, allocate more or less model.
    for band in (.10,.15):
        for w in (.0,.10,.25,.35,.50):
            add("E1_close_market",f"E1|within{int(band*100)}pp|model{round(w*100)}", "share","close",band,w)
    # E2: large V1.5 / market probability disagreement.
    for diff in (.10,.20,.30):
        for w in (.0,.10,.25,.35,.50):
            add("E2_market_disagreement",f"E2|gap{int(diff*100)}pp|model{round(w*100)}", "share","disagree",diff,w)
    # E3: significantly different prior-opponent strength (V1.5 SOS differential).
    # Replace 5/10 pp of the two 35% components by SOS when imbalance is large.
    for t in (.45,.80):
        for amount in (.03,.05,.10):
            add("E3_opponent_strength",f"E3|sosdiff{t}|shift{round(amount*100)}", "delta","sos",t,amount)
    # E4: offensive versus defensive rating separation; shift 3/5/10 pp
    # of V1.5 weight toward the MORE distinctive component, only for large imbalance.
    for t in (.4,.8):
        for amount in (.03,.05,.10):
            add("E4_offense_defense_mismatch",f"E4|imbalance{t}|shift{round(amount*100)}","delta","offdef",t,amount)
    # E5: prior home/road performance reliable and large enough to matter;
    # venue gains 5/10 pp sourced equally from offense and defense.
    for t in (.25,.50):
        for amount in (.05,.10):
            add("E5_venue_history",f"E5|venuesignal{t}|shift{round(amount*100)}","delta","venue",t,amount)
    # E6: fewer than 2/3/4/5 prior FBS games for either side:
    # hold on to preseason ratings by reducing current-season mix 10/20 pp.
    for t in (2,3,4,5):
        for amount in (.10,.20):
            add("E6_sample_reliability",f"E6|minGames{t}|curMinus{round(amount*100)}","delta","sample",t,amount)
    return out

def generate(df,spec):
    mhome=df.model_home.to_numpy(float)
    mk=df.market_home.to_numpy(float)
    cname=spec["condition"];t=spec["threshold"];a=spec["intensity"]
    off=df.offdiff.to_numpy(float);de=df.defdiff.to_numpy(float);so=df.sosdiff.to_numpy(float)
    venue=df.venue.to_numpy(float)
    if cname=="close":
        mask=np.abs(mk-.5)<=t
    elif cname=="disagree":
        mask=np.abs(mhome-mk)>=t
    elif cname=="sos":
        mask=(np.abs(so)>=t) & (df.min_prior_fbs.to_numpy()>=2)
    elif cname=="offdef":
        mask=(np.abs(np.abs(off)-np.abs(de))>=t)&(np.maximum(np.abs(off),np.abs(de))>=.75)
    elif cname=="venue":
        mask=(np.abs(venue)>=t)&(df.n_home_venue.to_numpy()>=2)&(df.n_away_venue.to_numpy()>=2)&(~df.neutral.to_numpy(bool))
    elif cname=="sample":
        mask=df.min_prior_fbs.to_numpy()<t
    else:raise ValueError(cname)
    if spec["kind"]=="share":
        w=np.where(mask,a,WEIGHT)
        p=w*mhome+(1-w)*mk
    else:
        if cname=="sos":
            delta=K*a*(so-.5*(off+de))
        elif cname=="offdef":
            shift=np.where(np.abs(off)>np.abs(de),1.0,-1.0)
            delta=K*a*shift*(off-de)
        elif cname=="venue":
            delta=K*a*(venue-.5*(off+de))
        elif cname=="sample":
            delta=-K*a*(.35*df.offcur_minus_prior.to_numpy(float)+
                    .35*df.defcur_minus_prior.to_numpy(float)+
                    .10*df.soscur_minus_prior.to_numpy(float))
        else:raise ValueError(cname)
        updated=expit(logit(np.clip(mhome,1e-9,1-1e-9))+np.where(mask,delta,0))
        p=WEIGHT*updated+(1-WEIGHT)*mk
    return p,mask

def analyze(df,spec):
    p,mask=generate(df,spec)
    baseline=df.base_testc.to_numpy(float)
    metrics_all=metrics(df,p)
    metrics_qualified=metrics(df.iloc[np.flatnonzero(mask)],p[mask]) if np.any(mask) else None
    reference_good=(baseline>=.5)==df.y.to_numpy(int)
    new_good=(p>=.5)==df.y.to_numpy(int)
    flip=(p>=.5)!=(baseline>=.5)
    return {**metrics_all,"qualified":int(mask.sum()),
            "qualifier_share":round(float(mask.mean()),4),
            "flips":int(flip.sum()),
            "fixes":int((flip&new_good).sum()),
            "broken":int((flip&reference_good).sum()),
            "delta_wins":int(new_good.sum()-reference_good.sum()),
            "delta_brier":round(float(metrics(df,baseline)["brier"]-metrics_all["brier"]),7),
            "qualified_metrics":metrics_qualified}

def main():
    full=features(prepare())
    years={y:full[full.year.eq(y)].copy() for y in (2024,2025,2026)}
    hold=years[2026][years[2026].week.isin([5,6])].copy()
    assert len(hold)==112
    original={str(y):metrics(df,df.base_testc) for y,df in years.items()}
    original["2026_frozen_weeks5_6"]=metrics(hold,hold.base_testc)
    specs=variants()
    results={}
    for item in specs:
        name=item["name"]
        results[name]={"spec":item,
          "train_2024":analyze(years[2024],item),
          "holdout_2025":analyze(years[2025],item),
          "recent_2026":analyze(years[2026],item),
          "frozen_2026_w5_6":analyze(hold,item)}
    selected={}
    for family in sorted(set(x["family"] for x in specs)):
        keys=[x["name"] for x in specs if x["family"]==family]
        # pre-specified control objective: 2024 min Brier, tie -> highest
        # 2024 winner count, then lexical deterministic tie breaker
        best=sorted(keys,key=lambda k:(results[k]["train_2024"]["brier"],
            -results[k]["train_2024"]["wins"],k))[0]
        selected[family]=best
    from collections import defaultdict
    reports={}
    for family in selected:
        arr=[(name,v) for name,v in results.items() if v["spec"]["family"]==family]
        reports[family]={
         "selected_2024":selected[family],
         "selection_train":results[selected[family]]["train_2024"],
         "validation_2025":results[selected[family]]["holdout_2025"],
         "recent_2026":results[selected[family]]["recent_2026"],
         "frozen_2026":results[selected[family]]["frozen_2026_w5_6"],
         "exploratory_best_2025":max(arr,key=lambda z:(z[1]["holdout_2025"]["delta_wins"],z[1]["holdout_2025"]["delta_brier"]))[0],
         "number_variants":len(arr)
        }
    out={"title":"Six conditional matchup model tests",
      "generated_utc":datetime.now(timezone.utc).isoformat(),
      "base_model_weight":WEIGHT,
      "cohorts":{str(y):len(x) for y,x in years.items()},
      "base_results":original,
      "training":"2024 only; select within each family by Brier; inspect 2025, 2026 unchanged",
      "details":results,"family_summary":reports,
      "notes":[
        "2024,2025 are retrospective model reconstructions, and 2026 W3/W4 also are; 2026 W5/W6 has frozen original model probabilities.",
        "Feature transformations and all challenger offsets are retrospective and computed using preweek historic datasets, not independently captured prospective predictions.",
        "Archived pregame opening sportsbook quotes have no independently authenticated first-published timestamp.",
        "The model development and calibration have previously used historical seasons, so 2025 is a temporal check rather than a pristine untouched holdout.",
        "E3 uses existing pregame SOS difference as an opponent-quality proxy; it is not a reconstructed strength of each past opposing defense.",
        "E4 uses offense-vs-defense statistical component imbalance, NOT direct rush-offense versus rush-defense or pass-matchup microstatistics.",
        "Six separate single-rule families are tested; combining the best rules would require a new interaction test and new holdout.",
        "Tests evaluate straight-up accuracy and proper win-probability scores, NOT against-spread, ROI, or tier bet records."
      ]}
    OUT.write_text(json.dumps(out,indent=2,allow_nan=False)+"\n")
    subset=["year","week","id","game","y","model_home","market_home","base_testc",
      "offdiff","defdiff","sosdiff","venue","min_prior_fbs","n_home_venue","n_away_venue","neutral"]
    flat=full[subset].copy()
    for family,best in selected.items():
        p,mask=generate(full,results[best]["spec"])
        flat["prediction_"+family]=p
        flat["flag_"+family]=mask
    flat.to_csv(GAMES,index=False)
    print("TEST_E_RESULTS "+json.dumps({
        "baseline":original,"selection_summary":reports,"n_candidates":len(specs)
    },sort_keys=True),flush=True)

if __name__=="__main__":
    main()
