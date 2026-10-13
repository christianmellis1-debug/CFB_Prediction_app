"""Test D2: Adjusted EPA missingness vs raw EPA fallback, FBS 2024–2026.

Research branch only: never change production V1.5, Test C or waterfall.
Selection uses 2024 Weeks 1–6 Brier, validation 2025 W1–6 plus
2024/25 full-season and 2026 archived W5–6 shadow sensitivity.

All candidate features use same completed, preceding-week team summaries.
Historical files are current reconstructions, NOT frozen historic predictions.
"""
import json, math, hashlib
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone
import pandas as pd
import numpy as np
from scipy.special import expit,logit
from scipy.stats import binomtest
import model_v1_5 as m
from matchup_advantages import normalize_fbs_schedule

ROOT=Path(__file__).resolve().parents[1]
SUM="https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_{}.csv"
SCHED="https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{}.csv"
HIST="https://raw.githubusercontent.com/christianmellis1-debug/CFB_Prediction_app/17a68114f48a4308d1e8312296537d701a65047b/research/test_c_historical_validation_games.csv"
RESULT=ROOT/"research/test_d_epa_fallback_results.json"
GAMES=ROOT/"research/test_d_epa_fallback_games.csv"

# Literal zero means ignore missing adjusted EPA; it is *not* a neutral
# replacement for other required features. Shrinks apply only on fallback.
MODES=("baseline","raw_all","missing_neutral","raw_shrink_25",
       "raw_shrink_50","raw_shrink_75","separate_standardization")
ORIGINAL=m.build_weekly_scores
WEIGHT=.16927926947215113

def finite(value):
    try:
        x=float(value)
        return x if math.isfinite(x) else None
    except (ValueError,TypeError,OverflowError):return None

def component_score(df, mode):
    if mode=="baseline":return ORIGINAL(df)
    scores={};weeks=defaultdict(list)
    for week,x in df.groupby("through_week"):
        z={}
        for key,(col,sign,fb) in m.COMPONENT_SPEC.items():
            value=pd.to_numeric(x[col],errors="coerce")
            if fb and fb in x.columns:
                raw=pd.to_numeric(x[fb],errors="coerce")
                missing=value.isna()
                if mode=="raw_all":
                    p=raw
                    zz=m._zscore(p*sign)
                elif mode=="missing_neutral":
                    zz=m._zscore(value*sign)
                    zz=zz.where(~missing,0.)
                elif mode.startswith("raw_shrink_"):
                    fraction={"raw_shrink_25":.25,"raw_shrink_50":.50,
                              "raw_shrink_75":.75}[mode]
                    zz=m._zscore(value.where(~missing,raw)*sign)
                    zz=zz.where(~missing,zz*fraction)
                elif mode=="separate_standardization":
                    adjz=m._zscore(value*sign)
                    rawz=m._zscore(raw*sign)
                    zz=adjz.where(~missing,rawz)
                else:raise ValueError(mode)
            else:
                zz=m._zscore(value*sign)
            z[key]=zz
        temp=pd.DataFrame({"team_id":x["team_id"].astype(int)})
        temp["off"]=.40*z["oe"]+.30*z["os"]+.15*z["ox"]+.15*z["or"]
        temp["defn"]=.40*z["de"]+.30*z["ds"]+.15*z["dx"]+.15*z["dr"]
        temp["sos"]=.5*z["so"]+.5*z["sd"]
        for _,r in temp.iterrows():
            tid=int(r["team_id"]);w=int(week)
            scores[(tid,w)]=(float(r["off"]),float(r["defn"]),float(r["sos"]))
            weeks[tid].append(w)
    for tid in weeks:weeks[tid]=sorted(set(weeks[tid]))
    return scores,weeks

def run_variant(now,prior,schedule,week,mode):
    try:
        m.build_weekly_scores=lambda df: component_score(df,mode)
        result=m.predict_week(now,prior,schedule,week,include_completed=True)
        return {str(int(r["Game ID"])):float(r["Home Win %"]) for _,r in result.iterrows()}
    finally:
        m.build_weekly_scores=ORIGINAL

def metric(rows,key,sample=None):
    d=rows if sample is None else [r for r in rows if sample(r)]
    if not d:return None
    yy=np.array([r["y"] for r in d],dtype=int)
    pp=np.array([r["prob"][key] for r in d],dtype=float)
    p0=np.array([r["prob"]["baseline"] for r in d],dtype=float)
    pred=pp>=.5
    good=pred==yy
    changed=pred!=(p0>=.5)
    ll=-yy*np.log(np.clip(pp,1e-12,1-1e-12))-(1-yy)*np.log(np.clip(1-pp,1e-12,1-1e-12))
    return dict(n=len(d),wins=int(good.sum()),losses=int((~good).sum()),accuracy=round(float(good.mean()),6),
      brier=round(float(np.mean((pp-yy)**2)),6),log_loss=round(float(np.mean(ll)),6),
      flips=int(changed.sum()),fixed=int((changed&good).sum()),broken=int((changed&(~good)).sum()))

def cohort(rows):
    cats={
     "all":lambda r:True,
     "early_weeks1_6":lambda r:r["week"]<=6,
     "late_weeks7plus":lambda r:r["week"]>=7,
     "one_or_both_missing_adj_epa":lambda r:r["missing_adj"],
     "one_or_both_raw_fallback_available":lambda r:r["used_raw"],
     "missing_adjusted_but_raw_available":lambda r:r["missing_adj_raw_present"],
     "adjusted_epa_for_both_teams":lambda r:not r["missing_adj"],
     "off_epa_missing_either":lambda r:r["missing_off"],
     "def_epa_missing_either":lambda r:r["missing_def"],
     "both_teams_four_fbs_prior_games":lambda r:r["min_prior_fbs"]>=4,
     "one_team_under_two_fbs_prior":lambda r:r["min_prior_fbs"]<2,
    }
    return {k:{mode:metric(rows,mode,fn) for mode in MODES}
       for k,fn in cats.items() if any(fn(x) for x in rows)}

def describe_missing(current,schedule,week):
    before=current[pd.to_numeric(current.through_week,errors="coerce").lt(week)]
    before=before.sort_values("through_week").drop_duplicates("team_id",keep="last")
    last={int(r.team_id):r for _,r in before.iterrows()}
    history=schedule[(pd.to_numeric(schedule.week,errors="coerce")<week) &
        schedule.season_type.astype(str).str.lower().eq("regular") &
        schedule.completed.astype(str).str.lower().isin(["true","t","1","yes","y"]) &
        schedule.home_points.notna()&schedule.away_points.notna()]
    count=Counter()
    for _,g in history.iterrows():count[int(g.home_id)]+=1;count[int(g.away_id)]+=1
    def get(tid):
        x=last.get(int(tid))
        if x is None:return {"no_row":True,"adj_off":False,"adj_def":False,"raw_off":False,"raw_def":False,"prior_fbs":count[int(tid)]}
        return {"no_row":False,
         "adj_off":finite(x.get("adj_off_epa")) is not None,
         "adj_def":finite(x.get("adj_def_epa")) is not None,
         "raw_off":finite(x.get("EPAplay_off")) is not None,
         "raw_def":finite(x.get("EPAplay_def")) is not None,
         "prior_fbs":count[int(tid)]}
    return get,last

def getdata():
    sums={};schedules={};hashes={}
    for year in (2023,2024,2025,2026):
        x=pd.read_csv(SUM.format(year),low_memory=False)
        sums[year]=x[pd.to_numeric(x.season,errors="coerce").eq(year)].copy()
        hashes["summary"+str(year)]=hashlib.sha256(pd.util.hash_pandas_object(
          sums[year][["team_id","through_week","adj_off_epa","adj_def_epa","EPAplay_off","EPAplay_def"]],
          index=False).values.tobytes()).hexdigest()
    for year in (2024,2025,2026):
        raw=pd.read_csv(SCHED.format(year),low_memory=False)
        schedules[year]=normalize_fbs_schedule(raw)
        hashes["schedule"+str(year)]=hashlib.sha256(pd.util.hash_pandas_object(
           raw[["game_id","week","home_id","away_id","home_points","away_points"]],
           index=False).values.tobytes()).hexdigest()
    return sums,schedules,hashes

def diag_all_sources(sums):
    out={}
    for year in (2024,2025,2026):
        x=sums[year].copy()
        for col in ("adj_off_epa","adj_def_epa","EPAplay_off","EPAplay_def"):
            x[col]=pd.to_numeric(x[col],errors="coerce")
        out[str(year)]={}
        for wk in sorted(x.through_week.dropna().astype(int).unique()):
            if year==2026 and wk>6:continue
            sub=x[x.through_week.eq(wk)]
            if len(sub)==0:continue
            off=sub.adj_off_epa.notna()
            de=sub.adj_def_epa.notna()
            rawoff=sub.EPAplay_off.notna()
            rawdef=sub.EPAplay_def.notna()
            pairedoff=sub[off&rawoff]
            paireddef=sub[de&rawdef]
            out[str(year)][str(wk)]={
               "rows":len(sub),"adj_off_available":int(off.sum()),"adj_def_available":int(de.sum()),
               "raw_off_available":int(rawoff.sum()),"raw_def_available":int(rawdef.sum()),
               "off_missing_raw_exists":int((~off&rawoff).sum()),
               "def_missing_raw_exists":int((~de&rawdef).sum()),
               "off_raw_adj_correlation":float(pairedoff.adj_off_epa.corr(pairedoff.EPAplay_off)) if len(pairedoff)>=5 else None,
               "def_raw_adj_correlation":float(paireddef.adj_def_epa.corr(paireddef.EPAplay_def)) if len(paireddef)>=5 else None
            }
    return out

def market_score(rows,mode):
    d=[r for r in rows if r.get("market_home") is not None]
    if not d:return None
    y=np.array([r["y"] for r in d],dtype=int)
    p=np.array([WEIGHT*r["prob"][mode]+(1-WEIGHT)*r["market_home"] for r in d])
    p0=np.array([WEIGHT*r["prob"]["baseline"]+(1-WEIGHT)*r["market_home"] for r in d])
    correct=(p>=.5)==y
    flipped=(p>=.5)!=(p0>=.5)
    ll=-y*np.log(np.clip(p,1e-12,1-1e-12))-(1-y)*np.log(np.clip(1-p,1e-12,1-1e-12))
    return dict(n=len(d),wins=int(correct.sum()),losses=int((~correct).sum()),
        accuracy=round(float(correct.mean()),6),brier=round(float(np.mean((p-y)**2)),6),
        log_loss=round(float(ll.mean()),6),flips=int(flipped.sum()),
        fixed=int((flipped&correct).sum()),broken=int((flipped&(~correct)).sum()))

def main():
    sums,schedules,hashes=getdata()
    archived=json.loads((ROOT/"data/shadow_tracking.json").read_text())
    odds=pd.read_csv(HIST,low_memory=False)
    odds=odds[odds.odds_source.eq("primary_open")]
    prices={(int(r.year),str(int(r.id))):float(r.market_home) for _,r in odds.iterrows()}
    rows=[]
    coverage={}
    for year,s in schedules.items():
        current=sums[year];prior=sums[year-1]
        s=s.copy()
        s["week"]=pd.to_numeric(s.week,errors="coerce")
        s["home_points"]=pd.to_numeric(s.home_points,errors="coerce")
        s["away_points"]=pd.to_numeric(s.away_points,errors="coerce")
        eligible=s[s.season_type.astype(str).str.lower().eq("regular")&
          s.completed.astype(str).str.lower().isin(["true","t","1","yes","y"]) &
          s.home_points.notna()&s.away_points.notna()&s.home_points.ne(s.away_points)]
        if year==2026:eligible=eligible[eligible.week.le(6)]
        coverage[str(year)]={"weeks":{}}
        for week in sorted(int(w) for w in eligible.week.unique()):
            games=eligible[eligible.week.eq(week)]
            if week>=18:continue
            prior_data,last=describe_missing(current,s,week)
            probs={mode:run_variant(current,prior,s,week,mode) for mode in MODES}
            for _,g in games.iterrows():
                gid=str(int(g.game_id))
                if gid not in probs["baseline"]:continue
                h=prior_data(int(g.home_id));a=prior_data(int(g.away_id))
                epamissing=any(not z[v] for z in (h,a) for v in ("adj_off","adj_def"))
                rawfallback=any((not z[adj]) and z[raw] for z in (h,a) for adj,raw in
                   (("adj_off","raw_off"),("adj_def","raw_def")))
                realbaseline=None;market=None
                frozen=False
                if year==2026 and week in (5,6):
                    q=archived["snapshots"].get(gid);outcome=archived["results"].get(gid) if q else None
                    if q and outcome and q["captured_at"]<q["kickoff"] and (
                       finite(outcome.get("home_score"))==finite(g.home_points) and
                       finite(outcome.get("away_score"))==finite(g.away_points)):
                        realbaseline=float(q["model_probability"])
                        if q["picked_side"]=="away":realbaseline=1-realbaseline
                        market=float(q["market_probability"])
                        if q["picked_side"]=="away":market=1-market
                        frozen=True
                elif year in (2024,2025):
                    market=prices.get((year,gid))
                base=probs["baseline"][gid]
                if frozen:
                    probs={mode:float(expit(logit(np.clip(realbaseline,1e-9,1-1e-9))+
                                 logit(np.clip(probs[mode][gid],1e-9,1-1e-9))-
                                 logit(np.clip(base,1e-9,1-1e-9)))) for mode in MODES}
                else:
                    probs={mode:probs[mode][gid] for mode in MODES}
                rows.append(dict(year=year,week=week,game_id=gid,
                  game=str(g.away_team)+" at "+str(g.home_team),
                  y=int(g.home_points>g.away_points),prob=probs,
                  missing_adj=epamissing,used_raw=rawfallback,
                  missing_adj_raw_present=rawfallback,
                  missing_off=not(h["adj_off"] and a["adj_off"]),
                  missing_def=not(h["adj_def"] and a["adj_def"]),
                  min_prior_fbs=min(h["prior_fbs"],a["prior_fbs"]),
                  frozen_baseline=frozen,market_home=market))
            coverage[str(year)]["weeks"][str(week)]=len(games)
            print("TEST_D_EPA_PROGRESS",year,week,len(games),flush=True)
    assert len([r for r in rows if r["year"]==2026 and r["frozen_baseline"]])==112
    match_2024=[r for r in rows if r["year"]==2024]
    match_2025=[r for r in rows if r["year"]==2025]
    match_2026=[r for r in rows if r["year"]==2026 and r["frozen_baseline"]]
    fit=[r for r in match_2024 if r["week"]<=6]
    hold=[r for r in match_2025 if r["week"]<=6]
    selected=min((metric(fit,mode)["brier"],mode) for mode in MODES)[1]
    out={"title":"Test D2 raw versus adjusted EPA fallback",
       "generated_utc":datetime.now(timezone.utc).isoformat(),
       "strategy":"Keep independent V1.5 formula/priors; change EPA scoring fallback only, inside each prior-week cross-sectional feature transform.",
       "candidate_descriptions":{
          "baseline":"Adj EPA, raw EPA fallback when missing, in one cross-sectional z-scoring group.",
          "raw_all":"Use raw EPA for every team even when adjusted exists.",
          "missing_neutral":"Missing adjusted EPA gets z=0; do not use raw.",
          "raw_shrink_25":"Existing mixed-source EPA z-score shrunk to 25% for missing adjusted value only.",
          "raw_shrink_50":"Existing mixed-source EPA z-score shrunk to 50% for missing adjusted value only.",
          "raw_shrink_75":"Existing mixed-source EPA z-score shrunk to 75% for missing adjusted value only.",
          "separate_standardization":"For missing adjusted EPA only, use separately standardized raw EPA z-score, avoiding mixed units."
       },
       "source_hashes":hashes,"coverage":coverage,
       "source_completeness":diag_all_sources(sums),
       "selection_rule":"Minimum 2024 Weeks1–6 Brier. Hold on 2025 Weeks1–6, 2025 full season and 2026 W5–6 frozen baseline plus retrospective log-odds correction.",
       "chosen_2024_early":selected,
       "v15":{
          "2024_week1_6":cohort(fit),
          "2025_week1_6":cohort(hold),
          "2024_all":cohort(match_2024),
          "2025_all":cohort(match_2025),
          "2026_week1_6":cohort([r for r in rows if r["year"]==2026]),
          "2026_frozen_week5_6":cohort(match_2026)},
       "test_c":{
           key:{mode:market_score(rr,mode) for mode in MODES}
           for key,rr in (("2024_early",fit),("2025_early",hold),
             ("2024_full",match_2024),("2025_full",match_2025),
             ("2026_frozen_w5_6",match_2026))},
       "limits":[
         "Weekly source data retrieved currently may differ from what was public before historical game starts.",
         "2026 modified V1.5 predictor probabilities are retrospective sensitivity adjustments to frozen V1.5 baselines, not separately frozen forecasts.",
         "Eligibility includes regular-season FBS-versus-FBS games; underlying cumulative summary statistics may include FCS competition.",
         "The source completeness check reflects last available pre-week team records; missing whole-team row distinct from absent adjusted EPA.",
         "2024 selection introduces tuning bias and previous V1.5 model weights used past-season data.",
         "Market quotes use different books (ESPN BET historically, original archived sportsbook in 2026).",
         "All financial/ROI/ATS results are out of scope and betting tiers are unaffected."
       ]}
    flat=[]
    for r in rows:
        d={k:v for k,v in r.items() if k!="prob"}
        d.update({f"p_{mode}":p for mode,p in r["prob"].items()})
        flat.append(d)
    pd.DataFrame(flat).to_csv(GAMES,index=False)
    RESULT.write_text(json.dumps(out,indent=2,allow_nan=False)+"\n")
    print("TEST_D_EPA_RESULT "+json.dumps({
      "chosen":selected,"base_2024":{k:metric(fit,k) for k in MODES},
      "hold_2025":{k:metric(hold,k) for k in MODES},
      "frozen_2026":{k:metric(match_2026,k) for k in MODES},
      "test_c_2024":out["test_c"]["2024_early"],
      "test_c_2025":out["test_c"]["2025_early"],
      "test_c_2026":out["test_c"]["2026_frozen_w5_6"]
    },sort_keys=True),flush=True)

if __name__=="__main__":main()
