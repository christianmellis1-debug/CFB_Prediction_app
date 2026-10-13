"""Test D: early-season data completeness, V1.5 prior weight and missing-data handling.

Isolated research: no production model, Test C market blend, or betting tier changes.
- 2024 selection on Weeks 1-6 only; unchanged candidates evaluated in 2025.
- 2026 frozen W5-6 base V1.5; replay model delta layered onto original
  saved pregame probabilities to avoid silently using reconstructed picks.
- Weekly advanced summaries can be retrospectively revised; no clean
  prospective holdout and no guaranteed pure-FBS play-by-play provenance.
"""
import json, hashlib, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import logit, expit
from matchup_advantages import normalize_fbs_schedule
import model_v1_5 as model

ROOT=Path(__file__).resolve().parents[1]
SUM="https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_{}.csv"
SCHED="https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{}.csv"
OUT=ROOT/"research/test_d_results.json"
GAMES=ROOT/"research/test_d_games.csv"
VARIANTS={
 "baseline":(0.0, False, "baseline"),
 "conservative_minus_10":(-.10,False,"delta"),
 "conservative_minus_20":(-.20,False,"delta"),
 "half_current_weight":(0.5,False,"ratio"),
 "aggressive_plus_10":(+.10,False,"delta"),
 "preserve_prior_when_no_snapshot":(0.,True,"baseline"),
 "conservative_minus_10_and_preserve_prior":(-.10,True,"delta")
}
ORIG_CUR=model.current_season_weight
ORIG_LAST=model._latest_snapshot
COMPONENTS=["adj_off_epa","adj_def_epa","success_off","success_def",
            "explosive_off","explosive_def","red_zone_success_off",
            "red_zone_success_def","off_strength_faced","def_strength_faced"]

def f(x):
    try:
        a=float(x)
        return a if math.isfinite(a) else None
    except (ValueError, TypeError, OverflowError):return None

def load():
    summaries={}; schedules={}; hashes={}
    for year in (2023,2024,2025,2026):
        d=pd.read_csv(SUM.format(year),low_memory=False)
        d=d[pd.to_numeric(d.season,errors="coerce").eq(year)].copy()
        summaries[year]=d
        hashes["summary"+str(year)]=hashlib.sha256(pd.util.hash_pandas_object(
            d[["team_id","through_week","adj_off_epa","adj_def_epa"]],index=False
        ).values.tobytes()).hexdigest()
    for year in (2024,2025,2026):
        d=pd.read_csv(SCHED.format(year),low_memory=False)
        schedules[year]=normalize_fbs_schedule(d)
        hashes["schedule"+str(year)]=hashlib.sha256(pd.util.hash_pandas_object(
            d[["game_id","week","home_id","away_id","home_points","away_points"]],index=False
        ).values.tobytes()).hexdigest()
    return summaries,schedules,hashes

def eligible_prior_schedule_count(s,week):
    w=pd.to_numeric(s.week,errors="coerce")
    done=s[(w<week)&s.completed.astype(str).str.lower().isin(
        ["true","t","1","yes","y"]) &
      s.season_type.astype(str).str.lower().eq("regular") &
      pd.to_numeric(s.home_points,errors="coerce").notna() &
      pd.to_numeric(s.away_points,errors="coerce").notna()]
    totals=defaultdict(int)
    for _,g in done.iterrows():
        totals[int(g.home_id)]+=1
        totals[int(g.away_id)]+=1
    return totals

def readiness(summary,s,week):
    past=summary[pd.to_numeric(summary.through_week,errors="coerce").lt(week)]
    past=past.sort_values("through_week").drop_duplicates("team_id",keep="last")
    byteam={int(r.team_id):r for _,r in past.iterrows()}
    prior_count=eligible_prior_schedule_count(s,week)
    def attributes(tid):
        prev=byteam.get(int(tid))
        if prev is None:return dict(no_snapshot=True,missing_adj_epa=True,
          missing_core_ge3=True,previous_fbs_games=prior_count[int(tid)])
        missing_epa=any(f(prev.get(col)) is None for col in ("adj_off_epa","adj_def_epa"))
        n=sum(f(prev.get(col)) is None for col in COMPONENTS)
        return dict(no_snapshot=False,missing_adj_epa=missing_epa,
          missing_core_ge3=n>=3,previous_fbs_games=prior_count[int(tid)])
    return attributes

def predict_variant(now,prior,schedule,week,key):
    delta,missing,change=VARIANTS[key]
    base_original=ORIG_CUR(week)
    def alt_weight(w):
        base=ORIG_CUR(w)
        if int(w)>6:return base
        if change=="delta":
            return max(.05,min(.95,base+delta))
        if change=="ratio":return base*delta
        return base
    if missing:
        prior_vec=model.build_prior_profiles(prior,schedule)
        def alt_snapshot(scores,weeks,tid,game_week):
            if not any(w<game_week for w in weeks.get(tid,[])):
                return prior_vec(tid)
            return ORIG_LAST(scores,weeks,tid,game_week)
    else:
        alt_snapshot=ORIG_LAST
    try:
        model.current_season_weight=alt_weight
        model._latest_snapshot=alt_snapshot
        df=model.predict_week(now,prior,schedule,week,include_completed=True)
        return {str(int(r["Game ID"])):float(r["Home Win %"]) for _,r in df.iterrows()}
    finally:
        model.current_season_weight=ORIG_CUR
        model._latest_snapshot=ORIG_LAST

def evaluate(rows,key,subset=None):
    frame=rows if subset is None else [r for r in rows if subset(r)]
    if not frame:return None
    y=np.array([r["y"] for r in frame],dtype=int)
    p=np.array([r["probs"][key] for r in frame],dtype=float)
    orig=np.array([r["probs"]["baseline"] for r in frame],dtype=float)
    correct=(p>=.5)==y
    changed=(p>=.5)!=(orig>=.5)
    log_loss=-y*np.log(np.clip(p,1e-12,1-1e-12))-(1-y)*np.log(np.clip(1-p,1e-12,1-1e-12))
    return dict(games=len(frame),wins=int(correct.sum()),losses=int((~correct).sum()),
        accuracy=round(float(correct.mean()),6),
        brier=round(float(np.mean((p-y)**2)),6),
        log_loss=round(float(log_loss.mean()),6),
        flips=int(changed.sum()),fixed=int((changed&correct).sum()),
        broken=int((changed&(~correct)).sum()))

def split_metrics(rows):
    categories={
        "all":lambda r:True,
        "any_missing_team_snapshot":lambda r:r["no_snapshot"],
        "both_team_snapshots_present":lambda r:not r["no_snapshot"],
        "any_missing_adjusted_epa":lambda r:r["missing_adj_epa"],
        "any_three_plus_missing_core_metrics":lambda r:r["missing_core_ge3"],
        "either_team_fewer_than_2_prior_fbs":lambda r:r["fbs_count_min"]<2,
        "both_teams_at_least_2_prior_fbs":lambda r:r["fbs_count_min"]>=2,
        "week1_2":lambda r:r["week"]<=2,
        "week3_4":lambda r:3<=r["week"]<=4,
        "week5_6":lambda r:5<=r["week"]<=6,
    }
    return {label:{key:evaluate(rows,key,fn) for key in VARIANTS}
        for label,fn in categories.items() if any(fn(r) for r in rows)}

def main():
    sums,schedules,hashes=load()
    archive=json.loads((ROOT/"data/shadow_tracking.json").read_text())
    rows=[];audits={}
    for year in (2024,2025,2026):
        s=schedules[year].copy()
        s.week=pd.to_numeric(s.week,errors="coerce")
        s.home_points=pd.to_numeric(s.home_points,errors="coerce")
        s.away_points=pd.to_numeric(s.away_points,errors="coerce")
        good=s[s.completed.astype(str).str.lower().isin(["true","t","1","yes","y"]) &
          s.season_type.astype(str).str.lower().eq("regular") &
          s.home_points.notna()&s.away_points.notna()&s.home_points.ne(s.away_points)]
        good=good[good.week.between(1,6)]
        counts={};modified=0
        for week in sorted(int(w) for w in good.week.unique()):
            subset=good[good.week.eq(week)]
            ready=readiness(sums[year],s,week)
            predicted={name:predict_variant(sums[year],sums[year-1],s,week,name)
                       for name in VARIANTS}
            counts[str(week)]={"games":len(subset)}
            for _,g in subset.iterrows():
                gid=str(int(g.game_id))
                base=predicted["baseline"].get(gid)
                if base is None:continue
                probs={}
                s0=archive["snapshots"].get(gid) if year==2026 and week in (5,6) else None
                final=archive["results"].get(gid) if s0 else None
                frozen=False
                if s0 and final and s0.get("captured_at") and s0.get("kickoff") and s0["captured_at"]<s0["kickoff"]:
                    if f(final.get("home_score"))==f(g.home_points) and f(final.get("away_score"))==f(g.away_points):
                        actual_base=float(s0["model_probability"])
                        if s0["picked_side"]=="away":actual_base=1-actual_base
                        frozen=True
                for name in VARIANTS:
                    p=predicted[name].get(gid)
                    if p is None:raise AssertionError(f"Missing candidate {name} game {gid}")
                    if frozen:
                        # Applying retrospective estimated incremental effect to
                        # immutable original prediction is a sensitivity proxy,
                        # not a genuinely captured challenger prediction.
                        p=float(expit(logit(np.clip(actual_base,1e-9,1-1e-9))+
                               logit(np.clip(p,1e-9,1-1e-9))-
                               logit(np.clip(base,1e-9,1-1e-9))))
                    probs[name]=p
                home=ready(int(g.home_id));away=ready(int(g.away_id))
                rows.append({"year":year,"week":week,"game_id":gid,
                  "game":str(g.away_team)+" at "+str(g.home_team),
                  "y":int(g.home_points>g.away_points),
                  "snapshot_source":"frozen_baseline_delta_proxy" if frozen else "retrospective_reconstruction",
                  "no_snapshot":home["no_snapshot"] or away["no_snapshot"],
                  "missing_adj_epa":home["missing_adj_epa"] or away["missing_adj_epa"],
                  "missing_core_ge3":home["missing_core_ge3"] or away["missing_core_ge3"],
                  "fbs_count_min":min(home["previous_fbs_games"],away["previous_fbs_games"]),
                  "probs":probs})
                if frozen:modified+=1
        audits[str(year)]={"weeks":counts,"frozen_2026_games":modified}
    primary2024=[r for r in rows if r["year"]==2024]
    primary2025=[r for r in rows if r["year"]==2025]
    primary2026=[r for r in rows if r["year"]==2026]
    valid=[r for r in primary2026 if r["snapshot_source"]=="frozen_baseline_delta_proxy"]
    selected=min((evaluate(primary2024,k)["brier"],k) for k in VARIANTS)[1]
    out={"title":"Test D Missing/limited statistical data and early-season weight",
       "created":datetime.now(timezone.utc).isoformat(),
       "sources":hashes,"variants":VARIANTS,"audits":audits,
       "design":"Baseline full V1.5 recreated on prior-week snapshots. Pick minimum 2024 Weeks1–6 Brier, then report unchanged 2025. 2026 W5–6 original frozen baseline plus retrospectively estimated variant log-odds deltas, not frozen challenger predictions.",
       "selected_on_2024":selected,
       "per_year":{str(y):split_metrics([r for r in rows if r["year"]==y])
           for y in (2024,2025,2026)},
       "frozen_2026_weeks5_6":split_metrics(valid),
       "combined_2024_2025":split_metrics(primary2024+primary2025),
       "weekly":{f"{y}-W{w}":{k:evaluate([r for r in rows if r["year"]==y and r["week"]==w],k)
                     for k in VARIANTS} for y in (2024,2025,2026) for w in range(1,7)},
       "limitations":[
          "Candidate selection and same-year comparison on 2024 cause model-selection bias.",
          "2024/25 historical predictions are retrospective, using published/revised weekly summaries.",
          "2026 Week5–6 candidate probabilities are approximations by anchoring retrospective log-odds effects to immutable baseline forecasts.",
          "The no-snapshot substitute uses the existing prior vector; missing metrics within an existing snapshot are unchanged.",
          "No test directly changes Test C market blend, tiers, moneyline outcomes, or profitability.",
          "A successful independent V1.5 candidate need not meaningfully improve market-dominated Test C."
       ]}
    OUT.write_text(json.dumps(out,indent=2,allow_nan=False)+"\n")
    flat=[]
    for r in rows:
        s={k:v for k,v in r.items() if k!="probs"}
        s.update({f"p_{k}":v for k,v in r["probs"].items()})
        flat.append(s)
    pd.DataFrame(flat).to_csv(GAMES,index=False)
    print("TEST_D_RESULT "+json.dumps({
       "selected":selected,"audits":audits,
       "2024":{k:evaluate(primary2024,k) for k in VARIANTS},
       "2025":{k:evaluate(primary2025,k) for k in VARIANTS},
       "2026frozen":{k:evaluate(valid,k) for k in VARIANTS},
       "missing_2024":out["per_year"]["2024"]["any_missing_team_snapshot"],
       "missing_2025":out["per_year"]["2025"]["any_missing_team_snapshot"]
    },sort_keys=True),flush=True)

if __name__=="__main__":main()
