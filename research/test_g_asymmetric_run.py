"""Test G — asymmetric bad run offense vs dominant run defense (pregame only).

Hypothesis: a team with bottom-quantile rushing YPC that faces a top-quantile
run defense (LOW opponent rushing YPC allowed) deserves a negative adjustment.

Separate 2024 development and 2025/2026 checks; identical 717/720/221
market-eligible games; original frozen V1.5 W5-6 2026, retrospectively
constructed matchup overlays. Never use opponent's performance *in the game*.
No change to production models/tiers.
"""
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime,timezone
import numpy as np
import pandas as pd
from scipy.special import logit, expit
from scipy.stats import binomtest
from test_f_rush_pass_matchups import (
 matched_cohort,boxes_clean,game_index,WEIGHT
)
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"research/test_g_asymmetric_run_results.json"
PER_GAME=ROOT/"research/test_g_asymmetric_run_games.csv"
CATS=("negative_only","positive_only","both_plus_minus")
THRESHOLDS=(.15,.25,.35,.40)
MIN_GAMES=(1,2,3)
BETAS=(0.,.05,.10,.20,.30,.50,.75)
YPC_GAPS=(0.,1.,1.5,2.)
# Given two teams' eligible earlier-FBS running profiles, compute cross-team
# standardized quantile rank across all known teams WITH preceding histories
# at the target week. Lower percentile means lower YPC offensive production
# or superior defensive yards per carry allowed.

def make_profiles(target_game, prior):
    d=prior.get(int(target_game),[])
    if not d:return None
    offense=np.sum([x["self"] for x in d],axis=0)
    opponents=np.sum([x["opp"] for x in d],axis=0)
    if offense[1]<=0 or opponents[1]<=0:return None
    return dict(games=len(d),off=float(offense[0]/offense[1]),
        defallowed=float(opponents[0]/opponents[1]))

def compute_features(cohort):
    features=[];coverage={}
    for year in (2024,2025,2026):
        schedule=game_index(year)
        id_rows=schedule.drop_duplicates("game_id").set_index("game_id")
        box,coverage[str(year)]=boxes_clean(year)
        prior=defaultdict(list)
        for game in schedule.itertuples(index=False):
            if (str(game.season_type).lower()!="regular" or
                str(game.completed).lower() not in ("true","t","1","yes","y") or
                not (np.isfinite(game.home_points) and np.isfinite(game.away_points)) or
                pd.isna(game.start)):
                continue
            h,a=int(game.home_id),int(game.away_id)
            hg=box.get((int(game.game_id),h));ag=box.get((int(game.game_id),a))
            if hg is None or ag is None:continue
            prior[h].append(dict(week=int(game.week),start=game.start,
                                 self=hg,opp=ag))
            prior[a].append(dict(week=int(game.week),start=game.start,
                                 self=ag,opp=hg))
        target=cohort[cohort.year.eq(year)]
        for week in sorted(target.week.unique()):
            games=target[target.week.eq(week)]
            # Profile by Week (not game score); all contributing FBS games
            # completed in an earlier week, thus eligible before any current
            # week matchup. For weeks with multiple games, do not use
            # this week's outcome to calculate percentiles.
            team_profiles={}
            for tid,items in prior.items():
                eligible=[x for x in items if x["week"]<week]
                pr=make_profiles(tid,{tid:eligible})
                if pr:team_profiles[tid]=pr
            if not team_profiles:
                for row in games.itertuples(index=False):
                    features.append(dict(year=year,id=int(row.id),
                        profile=False,nmin=0,home_off=np.nan,away_off=np.nan,
                        home_allowed=np.nan,away_allowed=np.nan,
                        home_off_pct=np.nan,away_off_pct=np.nan,
                        home_def_pct=np.nan,away_def_pct=np.nan))
                continue
            team_ids=list(team_profiles)
            off_values=np.array([team_profiles[t]["off"] for t in team_ids])
            def_values=np.array([team_profiles[t]["defallowed"] for t in team_ids])
            # percentile of all teams with a legitimate previous-FBS sample,
            # not percentiles derived from the target game's future outcomes.
            off_rank=pd.Series(off_values).rank(method="average",pct=True).to_numpy()
            def_rank=pd.Series(def_values).rank(method="average",pct=True).to_numpy()
            for i,tid in enumerate(team_ids):
                team_profiles[tid]["offpct"]=float(off_rank[i])
                team_profiles[tid]["defpct"]=float(def_rank[i])
            for row in games.itertuples(index=False):
                gid=int(row.id)
                if gid not in id_rows.index:raise AssertionError(f"Missing matchup {year}/{gid}")
                g=id_rows.loc[gid];hi,ai=int(g.home_id),int(g.away_id)
                # All team history used here is from strictly PRIOR weeks;
                # the percentile universe itself also uses only prior weeks.
                hp=team_profiles.get(hi);ap=team_profiles.get(ai)
                d=dict(year=year,id=gid,profile=bool(hp and ap),
                    nmin=min(hp["games"],ap["games"]) if hp and ap else 0,
                    home_off=hp["off"] if hp else np.nan,
                    away_off=ap["off"] if ap else np.nan,
                    home_allowed=hp["defallowed"] if hp else np.nan,
                    away_allowed=ap["defallowed"] if ap else np.nan,
                    home_off_pct=hp["offpct"] if hp else np.nan,
                    away_off_pct=ap["offpct"] if ap else np.nan,
                    home_def_pct=hp["defpct"] if hp else np.nan,
                    away_def_pct=ap["defpct"] if ap else np.nan)
                features.append(d)
            print("FEATURES",year,week,len(games),"teams prior",len(team_profiles),flush=True)
    f=pd.DataFrame(features)
    d=cohort.merge(f,on=["year","id"],validate="one_to_one")
    assert len(d)==len(cohort)==1658
    return d,coverage

def raw_mismatch(df,threshold,min_games,gap):
    eligible=(df.profile.to_numpy(bool) & df.nmin.ge(min_games).to_numpy(bool))
    ho=df.home_off_pct.to_numpy(float)
    ao=df.away_off_pct.to_numpy(float)
    hd=df.home_def_pct.to_numpy(float)
    ad=df.away_def_pct.to_numpy(float)
    # Defensive excellence: bottom-quartile YPC allowed, i.e. SMALL values.
    hn=eligible&(ho<=threshold)&(ad<=threshold)&(
        df.home_off.to_numpy(float)<=df.away_allowed.to_numpy(float)-gap)
    an=eligible&(ao<=threshold)&(hd<=threshold)&(
        df.away_off.to_numpy(float)<=df.home_allowed.to_numpy(float)-gap)
    # Positive mismatch: TOP 25% rushing offense vs BOTTOM 25% rushing defense
    # (last allowed percentile highest, i.e. weakness).
    hp=eligible&(ho>=1-threshold)&(ad>=1-threshold)&(
        df.home_off.to_numpy(float)>=df.away_allowed.to_numpy(float)+gap)
    ap=eligible&(ao>=1-threshold)&(hd>=1-threshold)&(
        df.away_off.to_numpy(float)>=df.home_allowed.to_numpy(float)+gap)
    return {"home_negative":hn,"away_negative":an,"home_positive":hp,
            "away_positive":ap,"qualifying_both_history":eligible}

def predict(df,category,threshold,min_games,gap,beta):
    pairs=raw_mismatch(df,threshold,min_games,gap)
    penalize= pairs["away_negative"].astype(float)-pairs["home_negative"].astype(float)
    benefit= pairs["home_positive"].astype(float)-pairs["away_positive"].astype(float)
    if category=="negative_only":adjust=penalize
    elif category=="positive_only":adjust=benefit
    elif category=="both_plus_minus":adjust=penalize+benefit
    else:raise ValueError(category)
    p=expit(logit(df.p_testc.to_numpy(float)) + beta*adjust)
    active=np.abs(adjust)>0
    counts={k:int(v.sum()) for k,v in pairs.items()}
    counts["net_active"]=int(active.sum())
    return p,counts,adjust,pairs

def metrics(df,p):
    yy=df.y.to_numpy(int);old=df.p_testc.to_numpy(float)
    good=(p>=.5)==yy;prev=(old>=.5)==yy;changed=(p>=.5)!=(old>=.5)
    fixed=int((changed&good).sum());broken=int((changed&(~good)).sum())
    return dict(games=len(df),correct=int(good.sum()),errors=int((~good).sum()),
       accuracy=round(float(good.mean()),6),
       brier=round(float(np.mean((p-yy)**2)),7),
       brier_delta=round(float(np.mean((old-yy)**2-(p-yy)**2)),7),
       switches=int(changed.sum()),fixed=fixed,broken=broken,
       p_exact=round(float(binomtest(fixed, fixed+broken,.5).pvalue),6) if fixed+broken else 1.0)

def analyze(df,c,base):
    p,counts,signal,pairs=predict(df,c["type"],c["threshold"],
                                  c["min_games"],c["gap"],c["beta"])
    return {**metrics(df,p),**counts}

def main():
    cohort=matched_cohort();df,coverage=compute_features(cohort)
    yearsets={str(y):df[df.year.eq(y)] for y in (2024,2025,2026)}
    yearsets["2026_frozen_w5_6"]=df[df.year.eq(2026)&df.week.isin([5,6])]
    assert len(yearsets["2026_frozen_w5_6"])==112
    base={k:metrics(v,v.p_testc.to_numpy(float)) for k,v in yearsets.items()}
    candidates={}
    for cat in CATS:
        for t in THRESHOLDS:
            for n in MIN_GAMES:
                for gap in YPC_GAPS:
                    for b in BETAS:
                        name=f"{cat}|q{int(t*100)}|min{n}|gap{gap:g}|beta{b:.2f}"
                        spec=dict(type=cat,threshold=t,min_games=n,gap=gap,beta=b)
                        candidates[name]=dict(config=spec,
                          train2024=analyze(yearsets["2024"],spec,base["2024"]),
                          check2025=analyze(yearsets["2025"],spec,base["2025"]),
                          check2026=analyze(yearsets["2026"],spec,base["2026"]),
                          frozen2026=analyze(yearsets["2026_frozen_w5_6"],spec,base["2026_frozen_w5_6"]))
    selected={}
    for cat in CATS:
        subset={k:v for k,v in candidates.items() if v["config"]["type"]==cat
                and v["train2024"]["net_active"]>=20 and v["train2024"]["switches"]>=1}
        if not subset:
            selected[cat]=None
            continue
        best=min(subset,key=lambda k:(
           subset[k]["train2024"]["brier"],
           -subset[k]["train2024"]["correct"],
           abs(subset[k]["config"]["beta"]),k))
        selected[cat]=best
    # Include diagnostic calibration of a disadvantaged-side probability:
    # opponent has strong defense; weak runner should win at rate matching
    # their baseline Test C chance unless a neglected residual exists.
    buckets={}
    for year,part in yearsets.items():
        basepair=raw_mismatch(part,.25,1,0.)
        mask=basepair["home_negative"]^basepair["away_negative"]
        if int(mask.sum())==0:continue
        under_home=basepair["home_negative"][mask]
        underdog_actual=np.where(under_home,part.loc[mask,"y"].to_numpy(int),
                                     1-part.loc[mask,"y"].to_numpy(int))
        underdog_expected=np.where(under_home,part.loc[mask,"p_testc"].to_numpy(float),
                                     1-part.loc[mask,"p_testc"].to_numpy(float))
        buckets[year]=dict(n=int(mask.sum()),weak_side_actual_wins=int(underdog_actual.sum()),
          weak_side_expected_wins=round(float(underdog_expected.sum()),3),
          actual_win_rate=round(float(underdog_actual.mean()),5),
          expected_win_rate=round(float(underdog_expected.mean()),5),
          residual_weak_minus_expected=round(float((underdog_actual-underdog_expected).mean()),6))
    results=dict(title="Test G asymmetric weak run offense vs strong run defense",
      created_utc=datetime.now(timezone.utc).isoformat(),
      baseline=base,coverage=coverage,year_sample={k:len(v) for k,v in yearsets.items()},
      candidate_count=len(candidates),selection_policy="Minimum 2024 Brier, requiring >=20 active and >=1 switched winner in 2024; one selection per rule family. 2025/2026 held chronologically apart.",
      selected={cat:({"key":key,"metrics":candidates[key]} if key else None)
                for cat,key in selected.items()},
      raw_weak_vs_strong_quartile_baseline=buckets,
      notes=[
       "All rates are computed only from earlier completed FBS-vs-FBS team boxes. Team percentiles are among only teams with valid preceding FBS history as of the target week.",
       "Weak rushing offense is bottom-q offensive YPC. Strong run defense is bottom-q opponents YPC allowed. No opponent-specific current-game box may enter the feature.",
       "An additional gap threshold ensures offensive YPC <= opposition defensive YPC allowed minus gap: this condition is a conservative magnitude screen but may exclude some excellent defenses.",
       "2024/2025 V1.5 reconstructed retrospectively; 2026 Weeks3-4 likewise. Weeks5-6 2026 original V1.5 frozen but candidate historical run statistics and opening prices remain retrospectively retrieved.",
       "ESPN BET 2024/25 and DraftKings 2026 historical opening quote timestamps not independently validated.",
       "The 2024 grid covers many correlated candidates; the selected result is optimistic in-sample and may be overfit.",
       "An eligible mismatch is not automatically evidence of independent value; opponent strength and market price already encode run defense.",
       "No production model or betting-tier changes."
      ],
      all_candidates=candidates)
    OUT.write_text(json.dumps(results,indent=2,allow_nan=False)+"\n")
    flat=df[["year","week","id","game","y","model_home","market_home","p_testc",
       "profile","nmin","home_off","away_off","home_allowed","away_allowed",
       "home_off_pct","away_off_pct","home_def_pct","away_def_pct"]].copy()
    for cat,key in selected.items():
        if key:
            sp=candidates[key]["config"]
            p,counts,signal,pairs=predict(df,sp["type"],sp["threshold"],
                                          sp["min_games"],sp["gap"],sp["beta"])
            flat[f"{cat}_adjusted_home"]=p
            flat[f"{cat}_signal"]=signal
            for k,v in pairs.items():flat[f"{cat}_{k}"]=v
    flat.to_csv(PER_GAME,index=False)
    print("TEST_G_RESULT "+json.dumps({
        "baseline":base,"selected":results["selected"],
        "quartile_residuals":buckets,"n_candidates":len(candidates)},sort_keys=True),flush=True)

if __name__=="__main__":main()
