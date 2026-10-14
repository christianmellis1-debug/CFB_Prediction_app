"""Small +/-2-point changes to V1.5 components, unchanged 16.9279% Test C blend.
Strict same-game 2026 W3-6 DK opening lines. W5-6 delta anchored to frozen baseline.
Retrospective reconstruction; no production edits.
"""
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import expit, logit
import model_v1_5 as model
from matchup_advantages import normalize_fbs_schedule
R=Path(__file__).resolve().parents[1]
S="https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_{}.csv"
SCH="https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_2026.csv"
G="https://raw.githubusercontent.com/christianmellis1-debug/CFB_Prediction_app/research/test-c-head-to-head-weeks3-6-2026-10-13/research/test_c_head_to_head_weeks3_6_games.csv"
W=.16927926947215113
orig=(model.OFFENSE_WEIGHT,model.DEFENSE_WEIGHT,model.VENUE_WEIGHT,model.SOS_WEIGHT)
names=("off","def","venue","sos")
versions={"baseline":orig}
for magnitude in (.01,.02):
 for a in range(4):
  for b in range(a+1,4):
   for sign in (1,-1):
    weights=list(orig)
    weights[a]+=magnitude*sign
    weights[b]-=magnitude*sign
    versions[f"{names[a]}{'+' if sign>0 else '-'}{int(100*magnitude)}_{names[b]}{'-' if sign>0 else '+'}{int(100*magnitude)}"]=tuple(weights)
assert len(versions)==25

def run(summary, prior, sched, week,weights):
  old=(model.OFFENSE_WEIGHT,model.DEFENSE_WEIGHT,model.VENUE_WEIGHT,model.SOS_WEIGHT)
  try:
   (model.OFFENSE_WEIGHT,model.DEFENSE_WEIGHT,model.VENUE_WEIGHT,model.SOS_WEIGHT)=weights
   return {str(int(r["Game ID"])):float(r["Home Win %"]) for _,r in model.predict_week(summary,prior,sched,week,include_completed=True).iterrows()}
  finally:
   (model.OFFENSE_WEIGHT,model.DEFENSE_WEIGHT,model.VENUE_WEIGHT,model.SOS_WEIGHT)=old

def scored(data,key):
  d=data.dropna(subset=[key])
  if d.empty:return None
  p=d[key].to_numpy(float);y=d.home_won.to_numpy(int)
  correct=(p>=.5)==y
  baseline=(d["blend_baseline"].to_numpy(float)>=.5)==y
  swapped=(p>=.5)!=(d["blend_baseline"].to_numpy(float)>=.5)
  return {"n":len(d),"wins":int(correct.sum()),"losses":int((~correct).sum()),
   "brier":float(np.mean((p-y)**2)),
   "logloss":float(np.mean(-y*np.log(np.clip(p,1e-12,1-1e-12))-(1-y)*np.log(np.clip(1-p,1e-12,1-1e-12)))),
   "flips":int(swapped.sum()),"fixed":int((swapped&correct).sum()),"broken":int((swapped&~correct).sum())}

def main():
 s=normalize_fbs_schedule(pd.read_csv(SCH,low_memory=False))
 now=pd.read_csv(S.format(2026),low_memory=False)
 prior=pd.read_csv(S.format(2025),low_memory=False)
 quoted=pd.read_csv(G,low_memory=False)
 quoted=quoted[quoted.has_open.astype(str).str.lower().eq("true")].copy()
 quoted["id"]=quoted.id.astype(str)
 assert len(quoted)==221
 assert quoted.week.value_counts().to_dict()=={3:53,4:56,5:56,6:56}
 predictions={}
 for w in (3,4,5,6):
  predictions[w]={}
  for tag,weights in versions.items():
   predictions[w][tag]=run(now,prior,s,w,weights)
  print("REBUILT_WEEK",w,flush=True)
 rows=[]
 for x in quoted.itertuples():
  gameid=str(x.id);week=int(x.week)
  base_recon=predictions[week]["baseline"].get(gameid)
  if base_recon is None:raise AssertionError("Baseline not found "+gameid)
  if week<=4:
   base=float(x.model_home)
   if not np.isclose(base,base_recon,atol=1e-10):raise AssertionError("W3/4 reconstruction disagreement "+gameid)
  else:
   base=float(x.model_home)
  row={"id":gameid,"week":week,"game":x.game,"home_won":int(x.home_won),
       "market_home":float(x.market_home),"original_home":base}
  for tag in versions:
   p=predictions[week][tag].get(gameid)
   if p is None:raise AssertionError("Missing "+tag+gameid)
   if week>=5:
    p=float(expit(logit(np.clip(base,1e-9,1-1e-9))+
                  logit(np.clip(p,1e-9,1-1e-9))-
                  logit(np.clip(base_recon,1e-9,1-1e-9))))
   row["model_"+tag]=p
   row["blend_"+tag]=W*p+(1-W)*float(x.market_home)
  rows.append(row)
 df=pd.DataFrame(rows)
 out={"method":"Unchanged total 100-point V1.5 weights, paired +/-1 and +/-2 point transfer across each component pair; locked 16.93/83.07 Test C; opening DK lines",
      "warning":"W3/W4 V1.5 retrospective, W5/W6 candidates are reconstruction-delta sensitivity anchored to frozen original V1.5; 2026 outcomes inspected for model selection.",
      "baseline_weights":dict(zip(names,orig)),"candidates":{k:dict(zip(names,v)) for k,v in versions.items()},
      "overall":{},"week":{},"frozen":{},"stat_model":{}}
 for tag in versions:
  out["overall"][tag]=scored(df,"blend_"+tag)
  out["frozen"][tag]=scored(df[df.week.ge(5)],"blend_"+tag)
  out["stat_model"][tag]=scored(df,"model_"+tag)
 for week in (3,4,5,6):
  out["week"][str(week)]={tag:scored(df[df.week.eq(week)],"blend_"+tag) for tag in versions}
 (R/"research/weight_micro_w3w6_results.json").write_text(json.dumps(out,indent=2)+"\n")
 df.to_csv(R/"research/weight_micro_w3w6_games.csv",index=False)
 print("RESULT_MICRO "+json.dumps({"baseline":out["overall"]["baseline"],"best_winner":sorted(out["overall"].items(),key=lambda x:(-x[1]["wins"],x[1]["brier"]))[:8],
    "best_brier":sorted(out["overall"].items(),key=lambda x:x[1]["brier"])[:8],
    "frozen":{k:out["frozen"][k] for k in list(versions)[:4]}},sort_keys=True),flush=True)
if __name__=="__main__": main()
