"""Test F: previous FBS rushing & passing offense vs opponent defense.

2024 select β and min-games by Brier, 2025 temporal validation,
2026 Weeks 3-6 sensitivity (W5-6 original frozen V1.5 baseline).
No production, waterfall or Test C coefficient changes.
"""
import json, math
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from scipy.special import expit, logit
from scipy.stats import binomtest
from matchup_advantages import normalize_fbs_schedule

ROOT=Path(__file__).resolve().parents[1]
SUM_BOX=("https://github.com/sportsdataverse/sportsdataverse-data/releases/"
  "download/espn_cfb_team_box/team_box_{}.csv")
SCHED=("https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/"
  "schedules/csv/cfb_schedules_{}.csv")
HIST=("https://raw.githubusercontent.com/christianmellis1-debug/"
  "CFB_Prediction_app/17a68114f48a4308d1e8312296537d701a65047b/"
  "research/test_c_historical_validation_games.csv")
NEW=("https://raw.githubusercontent.com/christianmellis1-debug/"
  "CFB_Prediction_app/research/test-c-head-to-head-weeks3-6-2026-10-13/"
  "research/test_c_head_to_head_weeks3_6_games.csv")
WEIGHT=.16927926947215113
OUT=ROOT/"research/test_f_matchups_results.json"
GAMES=ROOT/"research/test_f_matchups_games.csv"
FAMILIES=("run_yards_per_carry","passing_completion_rate",
          "passing_yards_per_attempt","run_plus_completion",
          "run_plus_pass_ypa","all_three")
BETAS=(-.25,-.10,0,.10,.25,.50,.75,1.0)
MINS=(1,2,3,4)

def matched_cohort():
    h=pd.read_csv(HIST,low_memory=False)
    h=h[h.odds_source.eq("primary_open")].copy()
    assert h.groupby("year").size().to_dict()=={2024:717,2025:720}
    hist=h[["year","week","id","game","y","model_home","market_home"]].copy()
    now=pd.read_csv(NEW,low_memory=False)
    now=now[now.has_open.eq(True)].copy()
    assert now.groupby("week").size().to_dict()=={3:53,4:56,5:56,6:56}
    current=now[["week","id","game","home_won","model_home","market_home"]].rename(columns={"home_won":"y"})
    current["year"]=2026
    d=pd.concat([hist,current],ignore_index=True)
    d["id"]=d.id.astype("int64")
    assert len(d)==1658 and not d.duplicated(["year","id"]).any()
    assert d.model_home.between(0,1,inclusive="neither").all()
    assert d.market_home.between(0,1,inclusive="neither").all()
    d["p_testc"]=WEIGHT*d.model_home+(1-WEIGHT)*d.market_home
    return d

def boxes_clean(year):
    x=pd.read_csv(SUM_BOX.format(year),low_memory=False)
    requested=["game_id","team_id","rushingYards","rushingAttempts",
               "netPassingYards","completionAttempts"]
    assert set(requested).issubset(x.columns),set(requested)-set(x.columns)
    x=x[requested].copy()
    for col in requested[:5]:
        x[col]=pd.to_numeric(x[col],errors="coerce")
    pairs=x.completionAttempts.astype(str).str.extract(r"^\s*(\d+)\s*[/−-]\s*(\d+)\s*$")
    x["comp"]=pd.to_numeric(pairs[0],errors="coerce")
    x["pass_att"]=pd.to_numeric(pairs[1],errors="coerce")
    counts=x.groupby(["game_id","team_id"]).size().rename("count").reset_index()
    duplicate=set(zip(counts.loc[counts["count"]>1,"game_id"].astype(int),
                      counts.loc[counts["count"]>1,"team_id"].astype(int)))
    x=x.dropna(subset=["game_id","team_id","rushingYards","rushingAttempts","netPassingYards","comp","pass_att"])
    x=x[(x.rushingAttempts>0)&(x.pass_att>0)&(x.comp>=0)&(x.comp<=x.pass_att)&
       (x.netPassingYards>=0)&(x.rushingYards>=-120)]
    out={}
    for r in x.itertuples(index=False):
        key=(int(r.game_id),int(r.team_id))
        if key in duplicate:continue
        out[key]=np.array([float(r.rushingYards),float(r.rushingAttempts),
            float(r.comp),float(r.pass_att),float(r.netPassingYards)],dtype=float)
    return out,dict(rows=len(x),valid_team_game_pairs=len(out),ambiguous_pairs=len(duplicate))

def game_index(year):
    s=normalize_fbs_schedule(pd.read_csv(SCHED.format(year),low_memory=False))
    s["game_id"]=pd.to_numeric(s.game_id,errors="coerce")
    s["week"]=pd.to_numeric(s.week,errors="coerce")
    s["home_id"]=pd.to_numeric(s.home_id,errors="coerce")
    s["away_id"]=pd.to_numeric(s.away_id,errors="coerce")
    s["start"]=pd.to_datetime(s.start_date,errors="coerce",utc=True)
    s["home_points"]=pd.to_numeric(s.home_points,errors="coerce")
    s["away_points"]=pd.to_numeric(s.away_points,errors="coerce")
    return s.dropna(subset=["game_id","week","home_id","away_id"]).copy()

def samples(row,team_id,prior_entries):
    """Sum FBS-only paired boxes from preceding weeks before matchup kickoff."""
    usable=[x for x in prior_entries.get(int(team_id),[])
            if x["week"]<int(row.week) and x["start"]<row.start]
    if not usable:return None
    own=np.sum([x["self"] for x in usable],axis=0)
    opp=np.sum([x["opponent"] for x in usable],axis=0)
    if min(own[1],own[3],opp[1],opp[3])<=0:return None
    return {
        "count":len(usable),"run_off":own[0]/own[1],
        "run_def":opp[0]/opp[1],
        "comp_off":own[2]/own[3],"comp_def":opp[2]/opp[3],
        "ypa_off":own[4]/own[3],"ypa_def":opp[4]/opp[3]
    }

def feature_table(cohort):
    details=[];stats={}
    for year in [2024,2025,2026]:
        s=game_index(year)
        index=s.drop_duplicates("game_id").set_index("game_id")
        lookup,stats[str(year)]=boxes_clean(year)
        hist=s[s.season_type.astype(str).str.lower().eq("regular")&
          s.completed.astype(str).str.lower().isin(["true","t","1","yes","y"])&
          s.home_points.notna()&s.away_points.notna()&s.start.notna()]
        prior=defaultdict(list)
        pairs_missing=0
        for g in hist.itertuples(index=False):
            gid=int(g.game_id);home=int(g.home_id);away=int(g.away_id)
            a=lookup.get((gid,home));b=lookup.get((gid,away))
            if a is None or b is None:
                pairs_missing+=1;continue
            for tid,own,opponent in ((home,a,b),(away,b,a)):
                prior[tid].append({"week":int(g.week),"start":g.start,
                                   "self":own,"opponent":opponent})
        stats[str(year)]["missing_paired_fbs_games"]=pairs_missing
        subset=cohort[cohort.year.eq(year)]
        for row in subset.itertuples(index=False):
            gid=int(row.id)
            if gid not in index.index:raise ValueError(f"Game ID missing {year}/{gid}")
            g=index.loc[gid]
            h=samples(g,int(g.home_id),prior)
            a=samples(g,int(g.away_id),prior)
            feat={"year":year,"id":gid,"run_diff":np.nan,
                  "comp_diff":np.nan,"ypa_diff":np.nan,"n_min":0,"eligible":False}
            if h is not None and a is not None:
                # Paired specific matchup: own offense against opponent's
                # prior defense, then home-vs-away expectation difference.
                run_home=.5*(h["run_off"]+a["run_def"])
                run_away=.5*(a["run_off"]+h["run_def"])
                comp_home=.5*(h["comp_off"]+a["comp_def"])
                comp_away=.5*(a["comp_off"]+h["comp_def"])
                ypa_home=.5*(h["ypa_off"]+a["ypa_def"])
                ypa_away=.5*(a["ypa_off"]+h["ypa_def"])
                feat.update(eligible=True,n_min=min(h["count"],a["count"]),
                    run_diff=float(run_home-run_away),
                    comp_diff=float(comp_home-comp_away),
                    ypa_diff=float(ypa_home-ypa_away))
            details.append(feat)
        print("FEATURES",year,"target games",len(subset),
              "complete paired profiles",sum(x["eligible"] for x in details if x["year"]==year),
              "missing FBS boxscore pairs",pairs_missing,flush=True)
    d=cohort.merge(pd.DataFrame(details),on=["year","id"],validate="one_to_one")
    assert len(d)==len(cohort)
    return d,stats

def signal(df,family):
    # Predeclared fixed scale units; no response-year refitting and no
    # postgame outcome entered into feature calculation.
    r=np.clip(df.run_diff.fillna(0).to_numpy(float)/2.0,-3,3)
    c=np.clip(df.comp_diff.fillna(0).to_numpy(float)/.15,-3,3)
    p=np.clip(df.ypa_diff.fillna(0).to_numpy(float)/3.0,-3,3)
    if family==FAMILIES[0]:return r
    if family==FAMILIES[1]:return c
    if family==FAMILIES[2]:return p
    if family==FAMILIES[3]:return (r+c)/2
    if family==FAMILIES[4]:return (r+p)/2
    if family==FAMILIES[5]:return (r+c+p)/3
    raise ValueError(family)

def prediction(df,family,min_prior,beta):
    mask=df.eligible.to_numpy(bool)&df.n_min.ge(min_prior).to_numpy(bool)
    orig=df.model_home.to_numpy(float)
    z=signal(df,family)
    estimated=expit(logit(np.clip(orig,1e-9,1-1e-9))+
          np.where(mask,beta*z,0.))
    testc=WEIGHT*estimated+(1-WEIGHT)*df.market_home.to_numpy(float)
    return estimated,testc,mask

def metrics(df,p,reference=None):
    y=df.y.to_numpy(dtype=int)
    p=np.clip(np.asarray(p,dtype=float),1e-12,1-1e-12)
    good=(p>=.5)==y
    out=dict(n=len(df),wins=int(good.sum()),losses=int((~good).sum()),
       accuracy=round(float(np.mean(good)),6),
       brier=round(float(np.mean((p-y)**2)),7),
       log_loss=round(float(np.mean(-y*np.log(p)-(1-y)*np.log(1-p))),7))
    if reference is not None:
        ref=(np.asarray(reference)>=.5)
        switch=(p>=.5)!=ref
        out.update(switched=int(switch.sum()),
           fixed=int((switch&good).sum()),
           broken=int((switch&(~good)).sum()))
    return out

def evaluate(df,family,n,beta):
    v15,blend,mask=prediction(df,family,n,beta)
    yv=metrics(df,v15,df.model_home)
    cv=metrics(df,blend,df.p_testc)
    cv["triggered"]=int(mask.sum())
    cv["delta_wins"]=cv["wins"]-int(((df.p_testc>=.5)==df.y).sum())
    cv["brier_gain"]=round(float(np.mean((df.p_testc.to_numpy()-df.y.to_numpy())**2)
                                  -cv["brier"]),7)
    yv["triggered"]=int(mask.sum())
    return {"v15":yv,"testc":cv}

def main():
    d,stats=feature_table(matched_cohort())
    years={y:d[d.year.eq(y)].copy() for y in (2024,2025,2026)}
    archive=years[2026][years[2026].week.isin([5,6])].copy()
    assert len(archive)==112
    baseline={str(y):{"v15":metrics(x,x.model_home),
                      "testc":metrics(x,x.p_testc)} for y,x in years.items()}
    baseline["2026_frozen_w5_6"]={"v15":metrics(archive,archive.model_home),
                                 "testc":metrics(archive,archive.p_testc)}
    output={"experiment":"Test F real rushing and passing opponent matchups",
       "created_utc":datetime.now(timezone.utc).isoformat(),
       "sources":{"box_csv":SUM_BOX,"schedules":SCHED},
       "source_coverage":stats,"n_by_year":{str(y):len(x) for y,x in years.items()},
       "base":baseline,"families":{},"notes":[
         "Only previously completed FBS-vs-FBS games are used; both teams' boxes must be valid before matchup week and kickoff.",
         "Passing YPA uses NET passing yards divided by attempts, not EPA; completion share is completions/attempts.",
         "Historical 2024/2025 V1.5 predictions are retrospectively reconstructed; 2026 W3/W4 same, W5/W6 uses frozen original V1.5 probabilities.",
         "Historical odds are retrospective archives: ESPN BET 2024/2025 and DraftKings 2026; original quoted pregame timestamp is not independently proven.",
         "This team box CSV does NOT have reliable sacks, pressures or OL pass-blocking measures; none are inferred. This test is rushing/passing matchup only.",
         "Study runs 2024 candidate development, selects by minimum Brier, reports 2025 and 2026 without refitting or retroactive production modifications.",
         "Comparisons cover quote-eligible identical games; no-availability matches retain baseline and do not count as new correct winners.",
         "Beta and minimum prior games are selected after 2024 outcomes, so retrospective selection bias remains.",
         "No deployment changes are authorized by this report."
       ]}
    for family in FAMILIES:
        tests={}
        for n in MINS:
            for beta in BETAS:
                key=f"min{n}|beta{beta:+.2f}"
                tests[key]={"configuration":{"min_fbs_games":n,"log_odds_coefficient":beta},
                    "development_2024":evaluate(years[2024],family,n,beta),
                    "validation_2025":evaluate(years[2025],family,n,beta),
                    "recent_2026":evaluate(years[2026],family,n,beta),
                    "frozen_w5w6_2026":evaluate(archive,family,n,beta)}
        selected=min(tests, key=lambda k:(
           tests[k]["development_2024"]["testc"]["brier"],
           -tests[k]["development_2024"]["testc"]["wins"],k))
        output["families"][family]={"selected_2024":selected,
            "selected_metrics":tests[selected],"candidates":tests}
    rows=d[["year","week","id","game","y","model_home","market_home",
      "p_testc","run_diff","comp_diff","ypa_diff","eligible","n_min"]].copy()
    for fam,record in output["families"].items():
        selected=record["selected_metrics"]["configuration"]
        v,p,trigger=prediction(d,fam,selected["min_fbs_games"],selected["log_odds_coefficient"])
        rows["challenger_"+fam]=p
        rows["flag_"+fam]=trigger
    OUT.write_text(json.dumps(output,indent=2,allow_nan=False)+"\n")
    rows.to_csv(GAMES,index=False)
    compact={family:{"selected":rec["selected_2024"],
       "2024":rec["selected_metrics"]["development_2024"],
       "2025":rec["selected_metrics"]["validation_2025"],
       "2026":rec["selected_metrics"]["recent_2026"],
       "2026_frozen":rec["selected_metrics"]["frozen_w5w6_2026"]}
       for family,rec in output["families"].items()}
    print("TEST_F_RESULTS "+json.dumps({"base":baseline,"selected":compact,
       "coverage":stats},sort_keys=True),flush=True)

if __name__=="__main__":
    main()
