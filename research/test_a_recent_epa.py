"""Test A2: isolated, strictly prior-week, opponent-adjusted last-three-game EPA.
Baseline: current model_v1_5 for reconstructed 2024/2025 games, immutable
archived V1.5 snapshot for 2026 games. Research only, no app import/mutation.
"""
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit, logit
import model_v1_5 as model

ROOT=Path(__file__).resolve().parents[1]
SOURCE="https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_{}.csv"
SCHEDULE="https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{}.csv"
WEIGHTS=[0,0.10,0.20,0.35,0.50]
MODES=["adjusted_both","adjusted_offense","adjusted_defense","raw_both"]
MIN_GAMES=4
OUT=ROOT/"research/test_a_recent_epa_results.json"
GAME_OUT=ROOT/"research/test_a_recent_epa_game_results.csv"
REQUIRED=["team_id","through_week","adj_off_epa","adj_def_epa","TEPA_off","TEPA_def","plays_off","plays_def"]
def f(x):
    try:
        q=float(x)
        return q if math.isfinite(q) else None
    except (TypeError,ValueError,OverflowError):
        return None
def fetch():
    summaries={};schedules={};sha={}
    for year in [2023,2024,2025,2026]:
        url=SOURCE.format(year)
        raw=pd.read_csv(url,low_memory=False)
        missing=set(REQUIRED)-set(raw.columns)
        if missing: raise ValueError(f"{year} missing summary fields: {sorted(missing)}")
        raw=raw[pd.to_numeric(raw.season,errors="coerce").eq(year)].copy()
        raw.team_id=pd.to_numeric(raw.team_id,errors="coerce")
        raw.through_week=pd.to_numeric(raw.through_week,errors="coerce")
        raw=raw.dropna(subset=["team_id","through_week"])
        raw=raw.drop_duplicates(["team_id","through_week"],keep=False)
        raw.team_id=raw.team_id.astype(int)
        raw.through_week=raw.through_week.astype(int)
        summaries[year]=raw
        sha[f"summary{year}"]=hashlib.sha256(pd.util.hash_pandas_object(raw[REQUIRED],index=False).values.tobytes()).hexdigest()
        if year>=2024:
            schedule=pd.read_csv(SCHEDULE.format(year),low_memory=False)
            schedule=model_schedule(schedule)
            schedules[year]=schedule
            sha[f"schedule{year}"]=hashlib.sha256(pd.util.hash_pandas_object(schedule[["game_id","week","home_id","away_id","home_points","away_points"]],index=False).values.tobytes()).hexdigest()
    return summaries,schedules,sha

def model_schedule(s):
    # Match normalization used by model_v1_5.predict_week.
    from matchup_advantages import normalize_fbs_schedule
    return normalize_fbs_schedule(s)

def summary_index(s):
    frames={}
    for _,r in s.iterrows():
        tid=int(r.team_id);w=int(r.through_week)
        frames[(tid,w)]=r
    wks=defaultdict(list)
    for t,w in frames:wks[t].append(w)
    for t in wks:wks[t].sort()
    return frames,wks

def latest(frames,weeks,tid,week):
    w=max((w for w in weeks.get(int(tid),[]) if w<week),default=None)
    return frames.get((int(tid),w)) if w is not None else None

def prior_index(s):
    frames,weeks=summary_index(s)
    return {tid:frames[(tid,max(ww))] for tid,ww in weeks.items()}

def ratings(opp,current,week,prior):
    p=latest(*current,opp,week)
    if p is None: p=prior.get(opp)
    if p is None:return None,None
    return f(p.get("adj_off_epa")),f(p.get("adj_def_epa"))

def incremental(team,week,current):
    frames,weeks=current
    now=frames.get((team,week))
    if now is None:return None
    prev=latest(frames,weeks,team,week)
    out={}
    for unit in ("off","def"):
        total=f(now.get("TEPA_"+unit));plays=f(now.get("plays_"+unit))
        if total is None or plays is None:return None
        prev_total=f(prev.get("TEPA_"+unit)) if prev is not None else 0.
        prev_plays=f(prev.get("plays_"+unit)) if prev is not None else 0.
        if prev_total is None or prev_plays is None:return None
        n=plays-prev_plays
        if n<15 or n>160:return None
        out[unit+"_plays"]=n
        out[unit+"_epa"]=(total-prev_total)/n
        if not math.isfinite(out[unit+"_epa"]):return None
    return out

def historical_records(season,schedule,summary,previous):
    # Cumulative weekly stats only represent a single game when a team
    # played exactly once in that calendar week, and that game was FBS.
    # Exclude team-weeks with concurrent/multiple games.
    current=summary_index(summary)
    prior=prior_index(previous)
    s=schedule.copy()
    s["week"]=pd.to_numeric(s.week,errors="coerce")
    s["home_points"]=pd.to_numeric(s.home_points,errors="coerce")
    s["away_points"]=pd.to_numeric(s.away_points,errors="coerce")
    done=s.completed.astype(str).str.lower().isin(["true","t","1","yes"])
    s=s[done & s.home_points.notna() & s.away_points.notna() & s.season_type.astype(str).str.lower().eq("regular")].copy()
    team_week=defaultdict(list)
    for _,g in s.iterrows():
        for side in ("home","away"): team_week[(int(g[side+"_id"]),int(g.week))].append(g)
    h=defaultdict(list)
    counts=defaultdict(int)
    for _,g in s.sort_values(["week","start_date"]).iterrows():
        w=int(g.week)
        for own,opp in [(int(g.home_id),int(g.away_id)),(int(g.away_id),int(g.home_id))]:
            if len(team_week[(own,w)])!=1:
                counts["multigame_teamweek"]+=1;continue
            inc=incremental(own,w,current)
            if inc is None:
                counts["missing_cumulative_epa"]+=1;continue
            opp_off,opp_def=ratings(opp,current,w,prior)
            if opp_off is None or opp_def is None:
                counts["missing_opponent_prior"]+=1;continue
            h[own].append({"week":w,"game_id":int(g.game_id),"off":inc["off_epa"],"def":inc["def_epa"],
              "adjusted_off":inc["off_epa"]-opp_def,"adjusted_def":inc["def_epa"]-opp_off,
              "off_plays":inc["off_plays"],"def_plays":inc["def_plays"]})
    for team in h:h[team].sort(key=lambda a:(a["week"],a["game_id"]))
    return h,dict(counts)

def weighted(rows,name,weight):
    return sum(r[name]*r[weight] for r in rows)/sum(r[weight] for r in rows)

def features(history,week):
    # Difference from entire eligible current-season history: avoid treating
    # the last three as a separate prediction, and compare only prior games.
    raw={}
    for tid,rows in history.items():
        prior=[r for r in rows if r["week"]<week]
        if len(prior)<MIN_GAMES:continue
        last=prior[-3:]
        item={}
        for prefix in ("","adjusted_"):
            for unit in ("off","def"):
                col=prefix+unit
                key="off_plays" if unit=="off" else "def_plays"
                val=weighted(last,col,key)-weighted(prior,col,key)
                item[col]=val
        raw[tid]=item
    if not raw:return {}
    fields=["off","def","adjusted_off","adjusted_def"]
    means={col:np.mean([item[col] for item in raw.values()]) for col in fields}
    stds={col:np.std([item[col] for item in raw.values()]) for col in fields}
    # Cross-sectional z-scores of recent-vs-season acceleration, not current
    # EPA levels; guard outliers and zero-variance weeks.
    return {tid:{col:float(np.clip((v[col]-means[col])/stds[col],-2.5,2.5)) if stds[col]>1e-9 else 0.
                 for col in fields} for tid,v in raw.items()}

def shift(g,feat,mode):
    h=feat.get(int(g.home_id));a=feat.get(int(g.away_id))
    if h is None or a is None:return None
    if mode=="raw_both":
        off=h["off"]-a["off"]; de=-(h["def"]-a["def"])
    else:
        off=h["adjusted_off"]-a["adjusted_off"];de=-(h["adjusted_def"]-a["adjusted_def"])
    if mode=="adjusted_offense":de=0
    if mode=="adjusted_defense":off=0
    return (model.CALIBRATION_SLOPE*1.10) * (model.OFFENSE_WEIGHT*off+model.DEFENSE_WEIGHT*de)

def metrics(rows,mode,weight):
    y=np.array([r["outcome"] for r in rows],dtype=float)
    p0=np.array([r["baseline"] for r in rows],dtype=float)
    adj=np.array([(r["shifts"].get(mode) or 0.) for r in rows],dtype=float)
    p=expit(logit(np.clip(p0,1e-8,1-1e-8))+weight*adj)
    changed=(p>=.5)!=(p0>=.5)
    common=(p>=.5)==y
    confidence=np.maximum(p,1-p)
    loss=-(y*np.log(np.clip(p,1e-12,1))+(1-y)*np.log(np.clip(1-p,1e-12,1)))
    n=len(rows)
    return {"games":n,"wins":int(common.sum()),"losses":int(n-common.sum()),
       "accuracy":round(float(common.mean()),5),"brier":round(float(np.mean((p-y)**2)),6),
       "log_loss":round(float(loss.mean()),6),"flips":int(changed.sum()),
       "fixed":int((changed & common).sum()),"broken":int((changed & ~common).sum()),
       "eligible_signal":sum(r["shifts"].get(mode) is not None for r in rows),
       "high_confidence_n":int((confidence>=.8).sum()),
       "high_confidence_wins":int(((confidence>=.8)&common).sum())}

def run():
    summaries,schedules,sha=fetch()
    archive=json.loads((ROOT/"data/shadow_tracking.json").read_text())
    rows=[];audit={}
    for season in [2024,2025,2026]:
        schedule=schedules[season];hist,counts=historical_records(season,schedule,summaries[season],summaries[season-1]);audit[str(season)]=counts
        s=schedule.copy();s.week=pd.to_numeric(s.week,errors="coerce")
        s.home_points=pd.to_numeric(s.home_points,errors="coerce")
        s.away_points=pd.to_numeric(s.away_points,errors="coerce")
        done=s.completed.astype(str).str.lower().isin(["true","t","1","yes"])
        s=s[done & s.home_points.notna() & s.away_points.notna() & s.home_points.ne(s.away_points)
            & s.season_type.astype(str).str.lower().eq("regular")].copy()
        for week in sorted(int(w) for w in s.week.unique() if 5<=w<=15):
            frame=s[s.week.eq(week)]
            feat=features(hist,week)
            if season<2026:
                base=model.predict_week(summaries[season],summaries[season-1],schedule,week,include_completed=True)
                base={str(int(r["Game ID"])):float(r["Home Win %"]) for _,r in base.iterrows()}
            else:base={}
            for _,g in frame.iterrows():
                gid=str(int(g.game_id))
                if season==2026:
                    locked=archive["snapshots"].get(gid);finished=archive["results"].get(gid)
                    if not locked or not finished or int(locked.get("week",-1))!=week:continue
                    if f(finished.get("home_score"))!=float(g.home_points) or f(finished.get("away_score"))!=float(g.away_points):continue
                    if not locked.get("captured_at") or not locked.get("kickoff") or locked["captured_at"]>=locked["kickoff"]:continue
                    baseline=locked["model_probability"] if locked["picked_side"]=="home" else 1-locked["model_probability"]
                else:baseline=base.get(gid)
                if baseline is None or not (0<baseline<1):continue
                shifts={mode:shift(g,feat,mode) for mode in MODES}
                rows.append({"season":season,"week":week,"id":gid,"away":g.away_team,"home":g.home_team,
                  "outcome":int(g.home_points>g.away_points),"baseline":float(baseline),"shifts":shifts,
                  "neutral":bool(g.neutral_site),"archived":season==2026})
    if not rows:raise AssertionError("No matching graded games")
    result={"experiment":"test-a2-three-game-opponent-adjusted-epa","generated_at":datetime.now(timezone.utc).isoformat(),
      "design":"First four+ earlier-season eligible FBS games; last three raw EPA differential versus season EPA, normalized across teams. Each opponent adjusted using ONLY earlier-week adjusted EPA or prior-season final EPA; never current-game or later-year opponent ratings. Weekly cumulative totals differenced using plays to estimate each eligible game's EPA. Compare frozen 2026 V1.5 and reconstructed earlier V1.5 on same games. Historical 2024-25 retrospectively revised feeds; no pristine independent holdout.",
      "source_hashes":sha,"audit":audit,"weights":WEIGHTS,"by_season":{},"by_week":{},"selected_using_2024":None,"validation":{}}
    for season in [2024,2025,2026]:
        selected=[r for r in rows if r["season"]==season]
        if selected:result["by_season"][str(season)]={"baseline":metrics(selected,"adjusted_both",0),
          "variants":{mode:{str(w):metrics(selected,mode,w) for w in WEIGHTS if w} for mode in MODES},
          "eligible_games":sum(r["shifts"]["adjusted_both"] is not None for r in selected)}
        for week in sorted(set(r["week"] for r in selected)):
            ss=[r for r in selected if r["week"]==week]
            result["by_week"][f"{season}-W{week}"]={"baseline":metrics(ss,"adjusted_both",0),
                "adjusted_both":{str(w):metrics(ss,"adjusted_both",w) for w in WEIGHTS if w}}
    # Select on 2024 Brier; evaluate unchanged on 2025 and 2026; never tune to 2026 results.
    train=[r for r in rows if r["season"]==2024]
    if train:
        candidates=[(metrics(train,mode,w)["brier"],mode,w) for mode in MODES for w in WEIGHTS if w]
        _,chosen_mode,chosen_weight=min(candidates)
        result["selected_using_2024"]={"mode":chosen_mode,"weight":chosen_weight}
        for season in [2024,2025,2026]:
            cohort=[r for r in rows if r["season"]==season]
            if cohort:result["validation"][str(season)]={"baseline":metrics(cohort,chosen_mode,0),"candidate":metrics(cohort,chosen_mode,chosen_weight)}
    pd.DataFrame([{k:v for k,v in r.items() if k!="shifts"}|{f"shift_{k}":v for k,v in r["shifts"].items()}
             for r in rows]).to_csv(GAME_OUT,index=False)
    OUT.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print("TEST_A2_RESULTS "+json.dumps({"by_season":result["by_season"],"selected_using_2024":result["selected_using_2024"],"validation":result["validation"],"audit":audit},sort_keys=True))
if __name__=="__main__":run()
