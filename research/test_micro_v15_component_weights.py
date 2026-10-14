"""Research-only Saturday Forecast V1.5 component weight micro-grid, 2026 W3-6.

Keep total 100% by transferring +/-1 or 2 percentage points between
two of OFFENSE/DEFENSE/VENUE/SOS while leaving others intact. Apply
each candidate to the *locked actual* V1.5 probability on W5-6
using the exactly reconstructed log-odds component delta. W3-4 use
historical reconstruction. Recalculate same quoted 16.93/83.07
Test C blended home probability without changing its external weights.
Never change production V1.5 or its betting tiers.
"""
import json, math
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import expit,logit
import model_v1_5 as m
from matchup_advantages import normalize_fbs_schedule

ROOT=Path(__file__).resolve().parents[1]
MATCHUPS_URL=("https://raw.githubusercontent.com/christianmellis1-debug/"
 "CFB_Prediction_app/research/test-c-head-to-head-weeks3-6-2026-10-13/"
 "research/test_c_head_to_head_weeks3_6_games.csv")
SUM=("https://github.com/sportsdataverse/sportsdataverse-data/releases/"
 "download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_{}.csv")
SCHEDULE=("https://raw.githubusercontent.com/sportsdataverse/"
 "cfbfastR-data/main/schedules/csv/cfb_schedules_2026.csv")
BASE={"offense":.35,"defense":.35,"venue":.20,"sos":.10}
LOCKED_BLEND_MODEL_WEIGHT=.16927926947215113
OUT=ROOT/"research/test_micro_weights_results.json"
GAME=ROOT/"research/test_micro_weights_games.csv"

def combinations_to_try():
    results={"official":BASE.copy()}
    for a,b in combinations(BASE,2):
        for point in (1,2):
            for sign in (-1,1):
                alt=BASE.copy()
                alt[a]+=sign*point/100.0
                alt[b]-=sign*point/100.0
                assert all(x>=0 for x in alt.values()) and abs(sum(alt.values())-1)<1e-8
                name=f"{a}{'+' if sign>0 else '-'}{point}pp__{b}{'-' if sign>0 else '+'}{point}pp"
                results[name]=alt
    return results

def metrics(frame,probs,reference=None):
    y=frame.y.to_numpy(dtype=int)
    pp=np.clip(np.asarray(probs,dtype=float),1e-12,1-1e-12)
    picks=(pp>=.5)
    good=(picks==y)
    score={"n":len(frame),"wins":int(good.sum()),"losses":int((~good).sum()),
      "accuracy":round(float(good.mean()),6),
      "brier":round(float(np.mean((pp-y)**2)),7),
      "log_loss":round(float(np.mean(-y*np.log(pp)-(1-y)*np.log(1-pp))),7)}
    if reference is not None:
        prior=np.asarray(reference,dtype=float)>=.5
        switched=picks!=prior
        score.update(flips=int(switched.sum()),
           fixes=int((switched&good).sum()),breaks=int((switched&(~good)).sum()))
    return score

def main():
    cohort=pd.read_csv(MATCHUPS_URL,low_memory=False)
    cohort=cohort[cohort.has_open.eq(True)].copy()
    assert len(cohort)==221
    assert cohort.groupby("week").size().to_dict()=={3:53,4:56,5:56,6:56}
    assert len(cohort.id.unique())==len(cohort)
    assert cohort.model_home.between(0,1,inclusive="neither").all()
    assert cohort.market_home.between(0,1,inclusive="neither").all()
    assert cohort.home_won.isin([0,1]).all()
    summ=pd.read_csv(SUM.format(2026),low_memory=False)
    prior=pd.read_csv(SUM.format(2025),low_memory=False)
    sch=normalize_fbs_schedule(pd.read_csv(SCHEDULE,low_memory=False))
    sch["id_str"]=pd.to_numeric(sch.game_id,errors="coerce").astype("Int64").astype(str)
    if sch.id_str.duplicated().any():raise AssertionError("schedule ID duplicates")
    games=sch.set_index("id_str")
    scores,weeks=m.build_weekly_scores(summ)
    profile=m.build_prior_profiles(prior,sch)
    components=[]
    for week in [3,4,5,6]:
        home_hist,road_hist=m._completed_history(sch,week)
        predicted=m.predict_week(summ,prior,sch,week,include_completed=True)
        check={str(int(x["Game ID"])):float(x["Home Win %"]) for _,x in predicted.iterrows()}
        for row in cohort[cohort.week.eq(week)].itertuples(index=False):
            gid=str(int(row.id))
            if gid not in games.index:raise AssertionError(f"Missing schedule row {gid}")
            g=games.loc[gid]
            if int(g.week)!=week:raise AssertionError(f"Week error {gid}")
            h,a=int(g.home_id),int(g.away_id)
            hs=m._latest_snapshot(scores,weeks,h,week)
            aws=m._latest_snapshot(scores,weeks,a,week)
            hp,ap=profile(h),profile(a)
            cur=m.current_season_weight(week)
            off=(1-cur)*(hp[0]-ap[0])+cur*(hs[0]-aws[0])
            de=(1-cur)*(hp[1]-ap[1])+cur*(hs[1]-aws[1])
            sos=(1-cur)*(hp[2]-ap[2])+cur*(hs[2]-aws[2])
            hm=(np.mean(home_hist[h]) if home_hist[h] else 0.0)
            am=(np.mean(road_hist[a]) if road_hist[a] else 0.0)
            venue=((hm*len(home_hist[h])/(len(home_hist[h])+3)-
                    am*len(road_hist[a])/(len(road_hist[a])+3))/14.0)
            if bool(g.get("neutral_site",False)):venue=0.0
            x={"offense":float(off),"defense":float(de),
               "venue":float(venue),"sos":float(sos)}
            score=sum(BASE[k]*x[k] for k in BASE)
            logit_p=m.CALIBRATION_SLOPE*1.10*score+m.conference_log_odds(g)
            rec=float(expit(logit_p))
            model_r=float(row.reconstructed_model_home)
            if abs(rec-model_r)>1e-8 or abs(rec-check[gid])>1e-8:
                raise AssertionError(f"Misaligned model replay for {gid}: computed {rec}, saved {model_r}, api {check[gid]}")
            if week<=4 and abs(rec-row.model_home)>1e-8:
                raise AssertionError(f"W3/4 base mismatch {gid}")
            if week>=5 and str(row.prediction_provenance)!="frozen":
                raise AssertionError(f"Must use frozen W5/6 baseline {gid}")
            components.append({"id":gid,"offense":x["offense"],"defense":x["defense"],
                "venue":x["venue"],"sos":x["sos"],"baseline_replay":rec,
                "conference_log_odds":m.conference_log_odds(g)})
    comp=pd.DataFrame(components)
    assert len(comp)==len(cohort)==221
    cohort["join"]=cohort.id.astype(str)
    comp["join"]=comp.id.astype(str)
    c=cohort.merge(comp,on="join",validate="one_to_one",suffixes=("","_weight"))
    assert len(c)==221
    rows=[]
    grid=combinations_to_try()
    inp=c.model_home.to_numpy(dtype=float)
    market=c.market_home.to_numpy(dtype=float)
    actual=c.home_won.to_numpy(dtype=int)
    reference=LOCKED_BLEND_MODEL_WEIGHT*inp+(1-LOCKED_BLEND_MODEL_WEIGHT)*market
    for name,weights in grid.items():
        # Historical component score is re-evaluated without re-fitting other
        # V1.5 coefficients. The delta in log odds is then applied to each
        # originally archived probability, never rewriting snapshots.
        delta=(m.CALIBRATION_SLOPE*1.10) * sum(
            (weights[k]-BASE[k])*c[k].to_numpy(dtype=float) for k in BASE)
        cand=expit(logit(np.clip(inp,1e-12,1-1e-12))+delta)
        blend=LOCKED_BLEND_MODEL_WEIGHT*cand+(1-LOCKED_BLEND_MODEL_WEIGHT)*market
        for idx,r in enumerate(c.itertuples()):
            rows.append({"variant":name,"game_id":int(r.id),"week":int(r.week),
              "game":r.game,"prediction_source":r.prediction_provenance,
              "y":int(r.home_won),"v15_home":float(cand[idx]),
              "testc_home":float(blend[idx]),"official_testc_home":float(reference[idx]),
              "official_v15_home":float(inp[idx]),
              "market_home":float(market[idx])})
    df=pd.DataFrame(rows)
    records={}
    for name,weights in grid.items():
        s=df[df.variant.eq(name)]
        records[name]={"weights":weights,
           "all":{"v15":metrics(s,s.v15_home,s.official_v15_home),
                  "testc":metrics(s,s.testc_home,s.official_testc_home)},
           "by_week":{str(week):{
               "v15":metrics(t,t.v15_home,t.official_v15_home),
               "testc":metrics(t,t.testc_home,t.official_testc_home)
               } for week in (3,4,5,6) for t in [s[s.week.eq(week)]]},
           "reconstructed_w3_4":{
               "v15":metrics(s[s.week.le(4)],s[s.week.le(4)].v15_home,s[s.week.le(4)].official_v15_home),
               "testc":metrics(s[s.week.le(4)],s[s.week.le(4)].testc_home,s[s.week.le(4)].official_testc_home)},
           "frozen_w5_6":{
               "v15":metrics(s[s.week.ge(5)],s[s.week.ge(5)].v15_home,s[s.week.ge(5)].official_v15_home),
               "testc":metrics(s[s.week.ge(5)],s[s.week.ge(5)].testc_home,s[s.week.ge(5)].official_testc_home)}
        }
    baseline=records["official"]
    assert baseline["all"]["v15"]["wins"]==158
    assert baseline["all"]["testc"]["wins"]==169
    assert baseline["frozen_w5_6"]["v15"]["wins"]==77
    assert baseline["frozen_w5_6"]["testc"]["wins"]==78
    for name in grid:
        if name=="official":continue
        if records[name]["all"]["testc"]["flips"] != records[name]["all"]["testc"]["fixes"]+records[name]["all"]["testc"]["breaks"]:
            raise AssertionError("Flips not reconciled")
    # Predefined selection on reconstructed W3-4. Evaluate on frozen W5-6
    # with no post-hoc criterion change.
    select=sorted(grid, key=lambda k:(
       -records[k]["reconstructed_w3_4"]["testc"]["wins"],
        records[k]["reconstructed_w3_4"]["testc"]["brier"],k))[0]
    # Independently report retrospective overall best; label post-hoc.
    opt=sorted(grid, key=lambda k:(
       -records[k]["all"]["testc"]["wins"],
        records[k]["all"]["testc"]["brier"],k))[0]
    out={"title":"2026 Weeks3–6 paired V1.5 micro-component-weight grid",
         "created_utc":datetime.now(timezone.utc).isoformat(),
         "grid":"Transfer 1 or 2 percentage points between any ordered pair of V1.5 offense/defense/venue/SOS. Sum stays 100%. Market blend stays 16.9279269/83.0720731.",
         "n_games":len(c),"n_variants":len(grid),
         "provenance":{
            "w3_w4":"Retrospective current-code V1.5 reconstruction checked exactly against pinned research predictions.",
            "w5_w6":"Original frozen pregame V1.5; reweighted candidate as retrospective log-odds delta without rewriting source.",
            "market":"Archived DraftKings opening no-vig paired odds from completed matching games; not independently timestamp-verified.",
            "data_url":MATCHUPS_URL,"model_current_code":True},
         "selection_on_reconstructed_weeks3_4":select,
         "exploratory_best_on_all_4_weeks":opt,
         "variants":records,
         "limitations":[
           "Weights are screened post-hoc on already resolved 2026 weeks, so a winner gain alone does not confirm future improvement.",
           "W5-W6 reweighted candidates are reconstructed log-odds deltas to real frozen original V1.5 probabilities, not archived independent challenger picks.",
           "The 2026 game set contains 221 paired-price matches; 6 W3/W4 lack valid odds and 2 W6 have no frozen base prediction.",
           "The Test C blend is very market-heavy, so a change in V1.5 may alter Brier without altering winners.",
           "Any promotion requires cross-year, genuinely unseen tests and no changes to the independently selected betting waterfall."
         ]}
    OUT.write_text(json.dumps(out,indent=2)+"\n")
    df.to_csv(GAME,index=False)
    summary=sorted([{"variant":k,"weights":v["weights"],
             "testc":v["all"]["testc"],"frozen":v["frozen_w5_6"]["testc"],
             "develop":v["reconstructed_w3_4"]["testc"]}
             for k,v in records.items()],
            key=lambda r:(-r["testc"]["wins"],r["testc"]["brier"]))
    print("TEST_WEIGHTS_RESULT "+json.dumps({"selection":select,"best_all":opt,
       "top_10":summary[:10],"official":records["official"],"variants":len(grid)},
       sort_keys=True),flush=True)
if __name__=="__main__":
    main()
