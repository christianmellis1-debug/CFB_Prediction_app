"""Strict pregame Test C head-to-head versus V1.5, 2026 FBS Weeks 3–6.

- Weeks 3–4: retrospectively reconstruct V1.5 from strictly earlier-week
  summaries (NOT contemporaneously frozen model predictions).
- Weeks 5–6: use immutable, captured-before-kickoff V1.5 snapshots.
- Market: both-sided DraftKings OPEN moneylines saved in public archived
  cfbfastR-cfb-raw game files, not a book timestamp independently attested.
- Evaluate exact warning: model team p>=.70, no-vig DK p<.55 for that team.
  Challenger changes winner to DK favorite ONLY when flagged. Also compare
  flag exclusion/abstention, hypothetical unconditional fade, pure DK and
  frozen 16.93%-model market blend.
- The 70/55 alert was discovered on Week 5–6 2026 outcomes and historically
  replicated retrospectively; Weeks 5–6 are NOT independent validation.
- Research only. No app/model/value-bet code mutation.
"""
import concurrent.futures, json, math, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from scipy.special import expit,logit
import model_v1_5 as model
from matchup_advantages import normalize_fbs_schedule

ROOT=Path(__file__).resolve().parents[1]
SUM="https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_{}.csv"
SCHEDULE="https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_2026.csv"
RAW="https://raw.githubusercontent.com/sportsdataverse/cfbfastR-cfb-raw/main/cfb/betting/json/{}.json"
OUT=ROOT/"research/test_c_head_to_head_weeks3_6_results.json"
GAME=ROOT/"research/test_c_head_to_head_weeks3_6_games.csv"
N=.16927926947215113

def num(x):
    try:
        z=float(x)
        return z if math.isfinite(z) else None
    except (ValueError,TypeError,OverflowError):return None
def money(x):
    if not isinstance(x,dict):return None
    line=x.get("moneyLine")
    if not isinstance(line,dict):return None
    price=num(line.get("american",line.get("alternateDisplayValue")))
    return price if price is not None and abs(price)>=100 else None
def implied(x):
    return 100/(100+x) if x>0 else -x/(100-x)

def odds(id):
    for attempt in range(3):
        try:
            with urlopen(Request(RAW.format(id),headers={"User-Agent":"SundayForecastResearch/1.0","Accept":"application/json"}),timeout=17) as h:
                data=json.load(h)
            items=(data.get("odds_full") or {}).get("items") or []
            choices=[a for a in items if (a.get("provider") or {}).get("name","").strip().lower()=="draftkings"]
            if not choices:return id,dict(error="no_draftkings",total_items=len(items))
            obj=choices[0]; h=obj.get("homeTeamOdds") or {};a=obj.get("awayTeamOdds") or {}
            result={}
            for phase in ["open","close"]:
                hp=money(h.get(phase));ap=money(a.get(phase))
                if hp is None or ap is None:continue
                p=implied(hp);q=implied(ap);vig=p+q-1
                if vig<0 or vig>.16:continue
                result[phase]={"home":p/(p+q),"home_ml":hp,"away_ml":ap,"vig":vig}
            return id,dict(prices=result,total_items=len(items))
        except HTTPError as e:
            if e.code in (404,410):return id,dict(error="not_found")
            error="HTTP_"+str(e.code)
        except (TimeoutError,URLError,OSError,ValueError) as e:error=type(e).__name__
        if attempt<2:time.sleep(.2*(attempt+1))
    return id,dict(error=error)

def stats(rows,col="model_home"):
    if not rows:return None
    y=np.array([int(r["home_won"]) for r in rows])
    p=np.clip(np.array([float(r[col]) for r in rows]),1e-12,1-1e-12)
    correct=(p>=.5)==y
    return dict(n=len(rows),wins=int(correct.sum()),losses=int(len(rows)-correct.sum()),
      accuracy=round(float(correct.mean()),5),brier=round(float(np.mean((p-y)**2)),6),
      log_loss=round(float(np.mean(-y*np.log(p)-(1-y)*np.log(1-p))),6))

def describe(rows):
    allrows=len(rows)
    obs=[r for r in rows if r["has_open"]]
    flags=[r for r in obs if r["warning"]]
    abstain=[r for r in obs if not r["warning"]]
    changers=[r for r in obs if (r["conditional_home"]>=.5)!=(r["model_home"]>=.5)]
    return dict(
      scheduled_model=stats(rows),dk_coverage_n=len(obs),dk_coverage_rate=round(len(obs)/allrows,5) if allrows else None,
      same_quote_cohort={name:stats(obs,field) for name,field in [
        ("v15","model_home"),("c_market_switch","conditional_home"),
        ("c_fade_every_warning","fade_home"),("market_only","market_home"),
        ("existing_1693_blend","blend1693_home"),("half_half","blend50_home")]},
      flags_n=len(flags),
      flags_model_correct=int(sum(r["model_correct"] for r in flags)),
      flags_model_incorrect=int(sum(not r["model_correct"] for r in flags)),
      flags_market_agrees=sum(r["market_agrees"] for r in flags),
      flags_market_disagrees=sum(not r["market_agrees"] for r in flags),
      baseline_after_exclusion=stats(abstain),
      remaining_games=len(abstain),
      switched_n=len(changers),
      switched_fixed=sum(r["c_correct"] and not r["model_correct"] for r in changers),
      switched_broken=sum(not r["c_correct"] and r["model_correct"] for r in changers),
      flagged_games=[{k:r[k] for k in ["id","week","game","model_picked_team","model_confidence",
        "market_on_pick","home_ml","away_ml","model_correct","market_agrees","c_correct"]}
        for r in flags],
      changed_games=[{k:r[k] for k in ["id","week","game","model_picked_team","model_confidence",
        "market_on_pick","model_correct","c_correct"]} for r in changers]
    )

def main():
    schedule=normalize_fbs_schedule(pd.read_csv(SCHEDULE,low_memory=False))
    schedule["week"]=pd.to_numeric(schedule.week,errors="coerce")
    games=schedule[schedule.week.isin([3,4,5,6]) &
                   schedule.season_type.astype(str).str.lower().eq("regular") &
                   schedule.completed.astype(str).str.lower().isin(["true","t","1","yes"]) &
                   schedule.home_points.notna() & schedule.away_points.notna() &
                   schedule.home_points.ne(schedule.away_points)].copy()
    if len(games)<200:raise AssertionError(f"Unexpected 2026 W3–6 game total: {len(games)}")
    print("MATCHUPS_FROM_SCHEDULE "+str(games.groupby("week").size().to_dict()),flush=True)
    summary={y:pd.read_csv(SUM.format(y),low_memory=False) for y in [2025,2026]}
    locked=json.loads((ROOT/"data/shadow_tracking.json").read_text())
    baselines={}
    for week in [3,4,5,6]:
        prediction=model.predict_week(summary[2026],summary[2025],schedule,week,include_completed=True)
        baselines[week]={str(int(r["Game ID"])):float(r["Home Win %"]) for _,r in prediction.iterrows()}
    candidates={}
    for _,g in games.iterrows():
        id=str(int(g.game_id));week=int(g.week)
        if week in (3,4):
            baseline=baselines[week].get(id);predtype="retrospective"
            if baseline is None:raise AssertionError("No reconstructed V1.5 for "+id)
        else:
            s=locked["snapshots"].get(id);o=locked["results"].get(id)
            if not s or not o:raise AssertionError("Missing frozen W5–6 "+id)
            if s.get("captured_at") is None or s.get("kickoff") is None or s["captured_at"]>=s["kickoff"]:
                raise AssertionError("Not pregame "+id)
            if num(o.get("home_score"))!=num(g.home_points) or num(o.get("away_score"))!=num(g.away_points):
                raise AssertionError("Score mismatch "+id)
            baseline=float(s["model_probability"]) if s["picked_side"]=="home" else 1-float(s["model_probability"])
            predtype="frozen"
        row={"id":id,"week":week,"game":str(g.away_team)+" at "+str(g.home_team),
          "home":str(g.home_team),"away":str(g.away_team),"home_won":int(float(g.home_points)>float(g.away_points)),
          "model_home":float(baseline),"model_confidence":max(baseline,1-baseline),
          "model_picked_team":str(g.home_team) if baseline>=.5 else str(g.away_team),
          "model_correct":int((baseline>=.5)==(float(g.home_points)>float(g.away_points))),
          "prediction_provenance":predtype,"reconstructed_model_home":baselines[week].get(id),
          "has_open":False,"has_close":False}
        candidates[id]=row
    fetched={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
        future=[pool.submit(odds,id) for id in candidates]
        for i,fut in enumerate(concurrent.futures.as_completed(future),1):
            id,prices=fut.result();fetched[id]=prices
            if i%50==0:print("ODDS_FILES "+str(i)+"/"+str(len(candidates)),flush=True)
    for id,row in candidates.items():
        oddsdata=fetched[id]
        row["odds_error"]=oddsdata.get("error")
        for phase in ["open","close"]:
            q=(oddsdata.get("prices") or {}).get(phase)
            row["has_"+phase]=q is not None
            if q is not None:
                row["dk_"+phase+"_home"]=q["home"]
                row["dk_"+phase+"_home_ml"]=q["home_ml"]
                row["dk_"+phase+"_away_ml"]=q["away_ml"]
        entry=(oddsdata.get("prices") or {}).get("open")
        if entry is None:continue
        market_home=entry["home"]
        confidence=row["model_confidence"]
        model_home=row["model_home"]
        chosen_home=model_home>=.5
        market_on_pick=market_home if chosen_home else 1-market_home
        flag=(confidence>=.7 and market_on_pick<.55)
        market_agrees=(chosen_home==(market_home>=.5))
        # If the market still weakly agrees, do not switch winner.
        conditional=market_home if flag and not market_agrees else model_home
        # An aggressive diagnostic variant: invert every warned pick,
        # even when sportsbook favorite matches model; not a recommendation.
        fade=1-model_home if flag else model_home
        blend=N*model_home+(1-N)*market_home
        row.update({"market_home":market_home,"market_on_pick":market_on_pick,
            "market_agrees":bool(market_agrees),"warning":bool(flag),
            "home_ml":entry["home_ml"],"away_ml":entry["away_ml"],
            "conditional_home":conditional,
            "fade_home":fade,"blend1693_home":blend,"blend50_home":.5*(model_home+market_home),
            "c_correct":int((conditional>=.5)==bool(row["home_won"]))})
    allrows=list(candidates.values())
    pd.DataFrame(allrows).to_csv(GAME,index=False)
    result={"name":"Test C alert and challenger vs V1.5, 2026 Weeks 3–6",
       "generated_utc":datetime.now(timezone.utc).isoformat(),
       "definition":{"warning":"V1.5 chosen winner >=70%; no-vig DraftKings OPEN probability same team <55%",
         "market_switch":"Change only flagged winners when DK favorite is the opposite side",
         "fade":"Invert every flagged winner, regardless of DK favorite (diagnostic only)",
         "abstain":"Exclude flagged picks; report remaining pick accuracy and coverage",
         "blend":"Re-pick blended home probability, 16.9279269% V1.5 and 83.0720731% DK",
         "week3_4":"V1.5 retrospection from prior-week 2026 summaries currently published",
         "week5_6":"frozen pregame original V1.5 snapshots with score verification"},
       "cautions":["Threshold was chosen after studying Weeks 5–6 2026; Week 5–6 is in-sample",
         "Weeks 3–4 use retrospective V1.5, not locked game-day forecasts; no genuinely prospective out-of-sample test in this comparison",
         "Betting raw archive opening lines can be edited/revised and lack independent publication timestamps",
         "Market prices may be absent for some games; headline head-to-head uses only common quoted games",
         "The warning is a rare event; forced flips and abstention cannot be interpreted as betting profitability"],
       "data_audit":{"schedule_total":len(games),"total_with_open":sum(r["has_open"] for r in allrows),
                     "total_with_close":sum(r["has_close"] for r in allrows),
                     "frozen":sum(r["prediction_provenance"]=="frozen" for r in allrows),
                     "retrospective":sum(r["prediction_provenance"]=="retrospective" for r in allrows),
                     "odds_failure_reasons":dict(pd.Series([r["odds_error"] for r in allrows if r["odds_error"]]).value_counts())},
       "by_week":{str(w):describe([r for r in allrows if r["week"]==w]) for w in [3,4,5,6]},
       "all_weeks":describe(allrows),
       "w3_w4_retrospective":describe([r for r in allrows if r["week"]<=4]),
       "w5_w6_frozen":describe([r for r in allrows if r["week"]>=5])}
    # Closing-line sensitivity: reconstruct same warnings against archived DK closing lines,
    # and measure matched cohort only, without mixing opening and closing sources.
    closing=[]
    for r in allrows:
        if not r["has_close"]:continue
        p=r["dk_close_home"];base=r["model_home"]
        conf=r["model_confidence"];onpick=p if base>=.5 else 1-p
        warn=conf>=.7 and onpick<.55
        agree=(base>=.5)==(p>=.5)
        rr=dict(r,has_open=True,market_home=p,market_on_pick=onpick,warning=warn,
          market_agrees=agree,conditional_home=p if warn and not agree else base,
          c_correct=int(((p if warn and not agree else base)>=.5)==bool(r["home_won"])),
          fade_home=1-base if warn else base,blend1693_home=N*base+(1-N)*p,
          blend50_home=.5*(base+p))
        closing.append(rr)
    result["closing_line_sensitivity"]={"all":describe(closing),
      "by_week":{str(w):describe([r for r in closing if r["week"]==w]) for w in [3,4,5,6]}}
    OUT.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print("RESULT_TEST_C_W3_6 "+json.dumps({
      "audit":result["data_audit"],
      "all":{k:v for k,v in result["all_weeks"].items() if k not in ["flagged_games","changed_games"]},
      "weekly":{k:{a:b for a,b in v.items() if a not in ["flagged_games","changed_games"]} for k,v in result["by_week"].items()},
      "flagged":result["all_weeks"]["flagged_games"],
      "closing":{"flagged_n":result["closing_line_sensitivity"]["all"]["flags_n"],
                 "comparison":result["closing_line_sensitivity"]["all"]["same_quote_cohort"]}
      },sort_keys=True),flush=True)

if __name__=="__main__":main()
