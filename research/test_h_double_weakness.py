"""Test H — weak rushing AND passing attack vs a strong opposing run defense.

Strict FBS vs FBS, preceding-week team-box histories. Separate
2024 selection/2025 temporal test/2026 W3-6 + frozen W5-6. Nothing
in here alters the live Test C, V1.5 or six independent betting tiers.
"""
import json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import expit,logit
from scipy.stats import binomtest
from test_f_rush_pass_matchups import matched_cohort,boxes_clean,game_index

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"research/test_h_double_weak_results.json"
GAME=ROOT/"research/test_h_double_weak_games.csv"
QUANTILES=(.20,.25,.33,.40)
MIN_GAMES=(1,2,3)
BETAS=(-.3,-.15,0.,.10,.20,.35,.50,.75)
FAMILIES=(
 "run_and_pass_weak_vs_run_stop",
 "run_and_pass_weak_vs_run_and_pass_stop",
 "run_and_completion_weak_vs_run_stop",
 "run_and_completion_weak_vs_run_and_pass_stop",
)

def _profile(data):
    own=np.sum([x["self"] for x in data],axis=0)
    opp=np.sum([x["opp"] for x in data],axis=0)
    if min(own[1],own[3],opp[1],opp[3])<=0:return None
    return {
        "fbs_games":len(data),
        "off_run":float(own[0]/own[1]),
        "off_ypa":float(own[4]/own[3]),
        "off_comp":float(own[2]/own[3]),
        "def_run":float(opp[0]/opp[1]),
        "def_ypa":float(opp[4]/opp[3]),
        "def_comp":float(opp[2]/opp[3])
    }

def input_features(cohort):
    result=[];audit={}
    for year in (2024,2025,2026):
        schedule=game_index(year)
        by_game=schedule.drop_duplicates("game_id").set_index("game_id")
        box,audit[str(year)]=boxes_clean(year)
        history=defaultdict(list)
        missing_paired=0
        valid_games=schedule[
            schedule.season_type.astype(str).str.lower().eq("regular") &
            schedule.completed.astype(str).str.lower().isin(["true","t","1","yes","y"]) &
            schedule.home_points.notna() & schedule.away_points.notna() &
            schedule.start.notna()]
        for game in valid_games.itertuples(index=False):
            gid=int(game.game_id);h=int(game.home_id);a=int(game.away_id)
            bh=box.get((gid,h));ba=box.get((gid,a))
            if bh is None or ba is None:
                missing_paired+=1
                continue
            history[h].append({"week":int(game.week),"start":game.start,"self":bh,"opp":ba})
            history[a].append({"week":int(game.week),"start":game.start,"self":ba,"opp":bh})
        audit[str(year)]["missing_paired_fbs_boxes"]=missing_paired
        targets=cohort[cohort.year.eq(year)]
        for week in sorted(targets.week.unique()):
            this_week=targets[targets.week.eq(week)]
            prior_profiles={}
            for tid,team_history in history.items():
                usable=[x for x in team_history if x["week"]<int(week)]
                if usable:
                    pr=_profile(usable)
                    if pr:prior_profiles[tid]=pr
            if prior_profiles:
                all_ids=list(prior_profiles)
                for feature in ("off_run","off_ypa","off_comp","def_run","def_ypa","def_comp"):
                    ranks=pd.Series([prior_profiles[tid][feature] for tid in all_ids]
                                   ).rank(method="average",pct=True)
                    for i,tid in enumerate(all_ids):
                        prior_profiles[tid][feature+"_pct"]=float(ranks.iloc[i])
            for item in this_week.itertuples(index=False):
                gid=int(item.id)
                if gid not in by_game.index:raise AssertionError(f"Missing FBS schedule ID {year} {gid}")
                matchup=by_game.loc[gid]
                home=prior_profiles.get(int(matchup.home_id))
                away=prior_profiles.get(int(matchup.away_id))
                row={"year":year,"id":gid,"matched_history":bool(home and away),
                     "min_fbs_games":min(home["fbs_games"],away["fbs_games"]) if home and away else 0}
                for side,profile in (("home",home),("away",away)):
                    for key in ("off_run","off_ypa","off_comp","def_run","def_ypa","def_comp"):
                        row[f"{side}_{key}"]=profile[key] if profile else np.nan
                        row[f"{side}_{key}_pct"]=profile[key+"_pct"] if profile else np.nan
                result.append(row)
            print("TEST_H_FEATURES",year,int(week),"matchups",len(this_week),
                  "team profile pool",len(prior_profiles),flush=True)
    data=cohort.merge(pd.DataFrame(result),on=["year","id"],validate="one_to_one")
    assert len(data)==1658
    return data,audit

def flags(frame,family,q,min_games):
    e=frame.matched_history.to_numpy(bool) & frame.min_fbs_games.ge(min_games).to_numpy(bool)
    passcol="off_comp" if "completion" in family else "off_ypa"
    defcol="def_comp" if "completion" in family else "def_ypa"
    def side_flag(side,opposite):
        # Low YPC and LOW net YPA/comp are both bad offenses. Low allowed
        # is a strong defense. All ranks computed only from prior FBS data.
        weak_run=frame[f"{side}_off_run_pct"].le(q).to_numpy()
        weak_pass=frame[f"{side}_{passcol}_pct"].le(q).to_numpy()
        strong_run=frame[f"{opposite}_def_run_pct"].le(q).to_numpy()
        if "run_and_pass_stop" in family:
            strong_pass=frame[f"{opposite}_{defcol}_pct"].le(q).to_numpy()
        else:
            strong_pass=np.ones(len(frame),dtype=bool)
        return e&weak_run&weak_pass&strong_run&strong_pass
    h=side_flag("home","away")
    a=side_flag("away","home")
    return h,a

def apply(frame,family,q,min_games,beta,base_col="p_testc"):
    hn,an=flags(frame,family,q,min_games)
    # When both teams qualify, symmetric penalties cancel, avoiding a
    # fictional decisive advantage.
    adjustment=an.astype(float)-hn.astype(float)
    p0=np.clip(frame[base_col].to_numpy(float),1e-10,1-1e-10)
    p=expit(logit(p0)+beta*adjustment)
    return p,hn,an

def metrics(df,prob,base_col="p_testc"):
    y=df.y.to_numpy(int);prev=df[base_col].to_numpy(float)
    predicted=prob>=.5
    correct=predicted==y
    switched=(prob>=.5)!=(prev>=.5)
    fixed=int((switched&correct).sum());broken=int((switched&~correct).sum())
    score=round(float(np.mean((prob-y)**2)),7)
    base_score=round(float(np.mean((prev-y)**2)),7)
    return dict(n=len(y),correct=int(correct.sum()),incorrect=int((~correct).sum()),
                accuracy=round(float(correct.mean()),6),brier=score,
                brier_change=round(float(base_score-score),7),
                switches=int(switched.sum()),fixed=fixed,broken=broken,
                paired_p=round(float(binomtest(fixed,fixed+broken,.5).pvalue),5)
                 if fixed+broken else 1.0)

def threshold_diagnostics(part,q=.25,min_games=1):
    e=part.matched_history.to_numpy(bool)&part.min_fbs_games.ge(min_games).to_numpy()
    ho=part.home_off_run_pct.le(q).to_numpy()
    ao=part.away_off_run_pct.le(q).to_numpy()
    hp=part.home_off_ypa_pct.le(q).to_numpy()
    ap=part.away_off_ypa_pct.le(q).to_numpy()
    hd=part.home_def_run_pct.le(q).to_numpy()
    ad=part.away_def_run_pct.le(q).to_numpy()
    hpd=part.home_def_ypa_pct.le(q).to_numpy()
    apd=part.away_def_ypa_pct.le(q).to_numpy()
    masks={
      "rush_only_bad_vs_run_stop":(e&ho&ad,e&ao&hd),
      "double_offense_weak_vs_run_stop":(e&ho&hp&ad,e&ao&ap&hd),
      "double_offense_weak_vs_both_stop":(e&ho&hp&ad&apd,e&ao&ap&hd&hpd)
    }
    groups={}
    y=part.y.to_numpy(int);pr=part.p_testc.to_numpy(float)
    for kind,(hm,am) in masks.items():
        exactly_one=hm^am
        actual=np.where(hm[exactly_one],y[exactly_one],1-y[exactly_one])
        expected=np.where(hm[exactly_one],pr[exactly_one],1-pr[exactly_one])
        groups[kind]={
           "home_weak":int(hm.sum()),"away_weak":int(am.sum()),
           "one_side_disadvantaged":int(exactly_one.sum()),
           "double_flagged":int((hm&am).sum()),
           "weak_side_actual_wins":int(actual.sum()),
           "weak_side_expected_wins":round(float(expected.sum()),4),
           "actual_weak_side_win_rate":round(float(actual.mean()),5) if len(actual) else None,
           "expected_weak_side_win_rate":round(float(expected.mean()),5) if len(expected) else None
        }
    return groups

def main():
    data,audit=input_features(matched_cohort())
    years={str(y):data[data.year.eq(y)].copy() for y in (2024,2025,2026)}
    years["2026_frozen_w5_6"]=data[data.year.eq(2026)&data.week.isin([5,6])].copy()
    assert len(years["2026_frozen_w5_6"])==112
    baseline={label:metrics(part,part.p_testc.to_numpy(float)) for label,part in years.items()}
    eligible={k:int(v.matched_history.sum()) for k,v in years.items()}
    result={}
    # Avoid favoring an in-sample fluke: screen candidate rules in 2024
    # with at least FIVE one-sided active flags. Report eligibility separately
    # and acknowledge very low power for rare intersections.
    for fam in FAMILIES:
        opts={}
        for q in QUANTILES:
            for n in MIN_GAMES:
                for beta in BETAS:
                    name=f"q{round(q*100)}_min{n}_beta{beta:.2f}"
                    spec={"q":q,"min_games":n,"beta":beta}
                    vals={}
                    for label,part in years.items():
                        pp,hn,an=apply(part,fam,q,n,beta)
                        vals[label]={**metrics(part,pp),
                          "flagged_home":int(hn.sum()),
                          "flagged_away":int(an.sum()),
                          "active_one_sided":int((hn^an).sum()),
                          "both_weak":int((hn&an).sum())}
                    opts[name]={"config":spec,**vals}
        candidates={k:v for k,v in opts.items() if v["2024"]["active_one_sided"]>=5 and v["config"]["beta"]>0}
        selected=min(candidates,key=lambda k:(candidates[k]["2024"]["brier"],
                  -candidates[k]["2024"]["correct"],candidates[k]["config"]["beta"],k)) if candidates else None
        result[fam]={"selected_in_2024":selected,"selected_scores":opts[selected] if selected else None,
                     "n_candidates":len(opts),"candidates":opts}
    diag={label:threshold_diagnostics(part) for label,part in years.items()}
    # Incremental to the Test F (+0.10 YPA) leading research challenger.
    # Feature requires *both* games' prior-FBS net passing YPA; reuse the
    # observed raw rate difference and apply the same two-signal formulation.
    additional={}
    for label,part in years.items():
        home_ypa=(part.home_off_ypa.to_numpy(float)+part.away_def_ypa.to_numpy(float))/2
        away_ypa=(part.away_off_ypa.to_numpy(float)+part.home_def_ypa.to_numpy(float))/2
        sig=np.clip((home_ypa-away_ypa)/3,-3,3)
        sig=np.where(part.matched_history.to_numpy(bool),sig,0.)
        base_f=expit(logit(part.p_testc.to_numpy(float))+.10*sig)
        additional[label]={"passing_ypa_only":metrics(part,base_f),
                           "baseline_testc":baseline[label]}
        # Use one prespecified intuitive rule in the incremental analysis:
        # bottom 25% both offense YPC+YPA vs top 25% defense YPC, >=1 game,
        # +0.20 log-odds penalty to the weak side.
        tmp=part.copy();tmp["p_compare"]=base_f
        adj,hn,an=apply(tmp,"run_and_pass_weak_vs_run_stop",.25,1,.20,
                        base_col="p_compare")
        additional[label]["passing_ypa_plus_double_weak"]=metrics(tmp,adj,"p_compare")
        additional[label]["qualifying"]=int((hn^an).sum())
    out={
      "title":"Test H: bad rushing + bad passing offense vs strong run defense",
      "generated_utc":datetime.now(timezone.utc).isoformat(),
      "model_base":"Test C with fixed 16.9279269% V1.5 / 83.0720731% market",
      "cohorts":{k:len(v) for k,v in years.items()},
      "baseline":baseline,
      "paired_FBS_box_coverage":audit,
      "eligible_profiles":eligible,
      "predeclared_quartile_diagnostics":diag,
      "families":result,
      "incremental_vs_passing_YPA":additional,
      "limitations":[
        "2024 and 2025 V1.5 baseline probabilities are retrospectively reconstructed; 2026 W3/W4 reconstructed, W5/W6 original V1.5 frozen.",
        "Each challenger uses current archives of previously completed FBS-vs-FBS boxes strictly from earlier weeks; archives can have later revisions.",
        "Historical ESPN BET (2024/2025) and DraftKings (2026) opening odds are not independently authenticated to be the exact bettable snapshot seen live.",
        "Qualifying double-weakness samples can be small; screening many thresholds/coefficients on 2024 creates selection bias.",
        "Completion percentage alone is a noisy passing-efficiency proxy. Raw net passing yards per attempt preferred; this is not an independently measured pass-protection/sack rate.",
        "A rush/run-defense interaction may already be reflected in market or aggregate EPA and does not establish sportsbook betting value.",
        "No change to production Test C, V1.5, or six tier selections."
      ]
    }
    OUT.write_text(json.dumps(out,indent=2,allow_nan=False)+"\n")
    flat=data[["year","week","id","game","y","p_testc","model_home","market_home",
          "matched_history","min_fbs_games","home_off_run","away_off_run",
          "home_off_ypa","away_off_ypa","home_def_run","away_def_run",
          "home_def_ypa","away_def_ypa"]].copy()
    for fam,rec in result.items():
        if rec["selected_scores"]:
            conf=rec["selected_scores"]["config"]
            p,hn,an=apply(data,fam,conf["q"],conf["min_games"],conf["beta"])
            flat["adjusted_"+fam]=p
            flat["home_weak_"+fam]=hn
            flat["away_weak_"+fam]=an
    flat.to_csv(GAME,index=False)
    print("TEST_H_RESULT "+json.dumps({
       "baseline":baseline,
       "diagnostics":diag,
       "selected":{fam:{k:v for k,v in dat.items() if k in ("selected_in_2024","selected_scores","n_candidates")} for fam,dat in result.items()},
       "incremental":additional
    },sort_keys=True),flush=True)

if __name__=="__main__":
    main()
