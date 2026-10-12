"""Tier 6: Home Field Advantage, pregame handwritten offense + defense matchup.

Original 2026-10-12 historical implementation is preserved in the three
low-level source functions below. Offense and defense each use 40% EPA,
25% rushing, 15% passing, 10% turnovers and 10% explosive, blended with
the existing production prior using unchanged current-season weights.

Only eligible if home has both positive edges, non-neutral same-group matchup,
not P4/0.50–0.74 magnitude, and an authentic DK favorite moneyline > -500.
This module computes ONLY pregame checks. The betting-price rule is applied
in the existing waterfall selection function after checking two-sided odds.
"""
import numpy as np
import pandas as pd
import model_v1_5 as model
from prospective_weights import component_vectors, latest
from matchup_advantages import normalize_fbs_schedule

P4={"ACC","Big Ten","Big 12","SEC"}
G6={"American Athletic","Conference USA","Mid-American","Mountain West","Sun Belt"}
EPS=1e-10

def prepare_full_boxes(box):
    """Unique, internally consistent team box scores only."""
    required=("game_id","team_id","rushingYards","rushingAttempts",
              "completionAttempts","turnovers","fumblesLost","interceptions")
    if not set(required).issubset(box):
        raise ValueError("Full passing/rushing/turnover box inputs missing: "+
                         ", ".join(sorted(set(required)-set(box))))
    x=box[list(required)].copy()
    for c in required:
        if c!="completionAttempts":
            x[c]=pd.to_numeric(x[c],errors="coerce")
    parsed=x.completionAttempts.astype(str).str.extract(
        r"^\s*(\d+)\s*[/−-]\s*(\d+)\s*$"
    )
    x["completions"]=pd.to_numeric(parsed[0],errors="coerce")
    x["pass_attempts"]=pd.to_numeric(parsed[1],errors="coerce")
    numeric=["game_id","team_id","rushingYards","rushingAttempts",
             "turnovers","fumblesLost","interceptions","completions",
             "pass_attempts"]
    valid=np.isfinite(x[numeric]).all(axis=1)
    valid &= x.rushingAttempts.gt(0) & x.rushingAttempts.mod(1).eq(0)
    valid &= x.pass_attempts.gt(0) & x.pass_attempts.mod(1).eq(0)
    valid &= x.completions.ge(0)&x.completions.le(x.pass_attempts)&x.completions.mod(1).eq(0)
    valid &= x[["turnovers","fumblesLost","interceptions"]].ge(0).all(axis=1)
    valid &= x[["turnovers","fumblesLost","interceptions"]].mod(1).eq(0).all(axis=1)
    valid &= x.turnovers.eq(x.fumblesLost+x.interceptions)
    valid &= x.game_id.mod(1).eq(0)&x.team_id.mod(1).eq(0)
    valid &= ~x.duplicated(["game_id","team_id"],keep=False)
    return x[valid].set_index(["game_id","team_id"],verify_integrity=True)


def standardized_team_profiles(history,lookup):
    """Return six statistically distinct prior-week box features per team.

    Teams with ANY incomplete previous FBS match fail closed. This avoids
    showing a strong run defense from only its easier, available games.
    League normalization uses available eligible FBS teams, not only the
    subsequently graded games. Totals aggregate attempts, NOT average YPC.
    """
    totals={}
    encountered=set()
    invalid=set()
    completed=0
    invalid_games=0
    for _,g in history.iterrows():
        hid,aid=int(g.home_id),int(g.away_id)
        encountered.update((hid,aid))
        keys=((g.game_id,g.home_id),(g.game_id,g.away_id))
        if not all(k in lookup.index for k in keys):
            invalid.update((hid,aid))
            invalid_games+=1
            continue
        h,a=(lookup.loc[k] for k in keys)
        for tid,own,opp in ((hid,h,a),(aid,a,h)):
            totals.setdefault(tid,np.zeros(11,dtype=float))
            totals[tid]+=np.array([
                own.rushingYards,own.rushingAttempts,
                own.completions,own.pass_attempts,own.turnovers,
                opp.rushingYards,opp.rushingAttempts,
                opp.completions,opp.pass_attempts,opp.turnovers,1.0
            ])
        completed+=1
    eligible={tid:t for tid,t in totals.items()
              if tid not in invalid and t[10]>=1 and min(t[1],t[3],t[6],t[8])>0}
    quality={"completed_history_games":len(history),
             "accepted_complete_games":completed,
             "incomplete_box_games":invalid_games,
             "all_teams_seen":len(encountered),
             "teams_with_valid_full_history":len(eligible)}
    if len(eligible)<2:
        return {},quality
    ids=list(eligible)
    x=np.array([
        [t[0]/t[1],t[2]/t[3],t[4]/t[10],
         t[5]/t[6],t[7]/t[8],t[9]/t[10]]
        for t in eligible.values()
    ],dtype=float)
    means=x.mean(axis=0)
    sd=x.std(axis=0)
    if np.any(sd<=1e-10) or not np.isfinite(sd).all():
        raise ValueError("Incomplete/unvarying week-wide full-stat dispersion")
    # Off YPC+, off completion+, fewer giveaways+,
    # lower YPC allowed+, lower completions allowed+, more takeaways+.
    signs=np.array([+1,+1,-1,-1,-1,+1])
    z=(x-means)/sd*signs
    return dict(zip(ids,z)),quality


def published_required(summary, week):
    """Fail closed if a matchup team lacks the requested pregame EPA/explosive."""
    previous=summary[pd.to_numeric(summary.through_week,errors="coerce").lt(week)]
    prior=previous.sort_values("through_week").drop_duplicates("team_id",keep="last")
    out=set()
    for _,r in prior.iterrows():
        needed=[
            r.get("explosive_off"),r.get("explosive_def"),
            r.get("adj_off_epa") if pd.notna(r.get("adj_off_epa")) else r.get("EPAplay_off"),
            r.get("adj_def_epa") if pd.notna(r.get("adj_def_epa")) else r.get("EPAplay_def")
        ]
        if all(pd.notna(v) and np.isfinite(float(v)) for v in needed):
            out.add(int(r.team_id))
    return out



def group(conference,team,year):
    """Fail closed on independent, changed or unknown affiliations.

    2022-2023 Pac-12 is historic P4; 2024-2025 two-team Pac-12 is
    excluded as ambiguous; 2026 Pac-12 is G6 per present app policy.
    """
    name=str(team).strip().casefold()
    if name in {"notre dame","notre dame fighting irish"}:
        return "P4"
    conference=str(conference).strip()
    if conference in P4:
        return "P4"
    if conference in G6:
        return "G6"
    if conference=="Pac-12":
        return "P4" if year<=2023 else "G6" if year>=2026 else None
    return None




def build_tier6_checks(schedule, boxes, current_summary, prior_summary, week):
    """Independent pregame dual-advantage checks; fail closed if inputs are missing."""
    out={}
    try:
        week=int(week)
        if week<3 or any(x is None for x in (schedule,boxes,current_summary,prior_summary)):
            return out
        s=normalize_fbs_schedule(schedule).copy()
        required={"season","week","game_id","home_id","away_id","home_team","away_team",
                  "home_conference","away_conference","start_date","completed",
                  "neutral_site","season_type","home_points","away_points"}
        if not required.issubset(s) or s.empty:
            return out
        for col in ("season","week","game_id","home_id","away_id","home_points","away_points"):
            s[col]=pd.to_numeric(s[col],errors="coerce")
        s["start"]=pd.to_datetime(s.start_date,utc=True,errors="coerce")
        finished=s.completed.astype(str).str.strip().str.lower().isin(("true","t","1","1.0","yes","y"))
        years=s.season.dropna().unique()
        if len(years)!=1:
            return out
        year=int(years[0])
        slate=s[s.week.eq(week)].dropna(subset=["game_id","home_id","away_id"])
        if slate.empty or slate.start.isna().any():
            return out
        eligible=[]
        for game in slate.itertuples(index=False):
            gid=str(int(game.game_id))
            info={"status":"outside","qualifies":False}
            out[gid]=info
            if s.game_id.eq(game.game_id).sum()!=1:
                info["reason"]="Ambiguous game ID."
                continue
            if str(game.neutral_site).strip().lower() not in ("false","f","0","0.0","no","n"):
                info["reason"]="Neutral site or missing venue information."
                continue
            if str(game.season_type).strip().lower()!="regular":
                info["reason"]="Regular-season games only."
                continue
            hg=group(game.home_conference,game.home_team,year)
            ag=group(game.away_conference,game.away_team,year)
            if hg is None or hg!=ag:
                info["reason"]="Same-group P4/P4 or G6/G6 only."
                continue
            info.update(status="missing",group=hg,reason="Earlier-week advanced/box-score data missing.")
            eligible.append(game)
        if not eligible:
            return out
        first_time=slate.start.min()
        history=s[s.week.lt(week)&s.start.lt(first_time)&finished&
                  s.home_points.notna()&s.away_points.notna()]
        lookup=prepare_full_boxes(boxes)
        features,_=standardized_team_profiles(history,lookup)
        published=published_required(current_summary,week)
        if not features or not published:
            return out
        scores,weeks=component_vectors(current_summary)
        prior_vector=model.build_prior_profiles(prior_summary,s)
        cur_weight=model.current_season_weight(week)
        for game in eligible:
            gid=str(int(game.game_id))
            hid,aid=int(game.home_id),int(game.away_id)
            if hid not in features or aid not in features or hid not in published or aid not in published:
                continue
            hv,av=features[hid],features[aid]
            hc=latest(scores,weeks,hid,week)
            ac=latest(scores,weeks,aid,week)
            off=np.asarray(hc[0])-np.asarray(ac[0])
            deff=np.asarray(hc[1])-np.asarray(ac[1])
            hp,ap=prior_vector(hid),prior_vector(aid)
            custom_off=(.40*off[0]+.25*(hv[0]-av[0])+
                        .15*(hv[1]-av[1])+.10*(hv[2]-av[2])+.10*off[2])
            custom_def=(.40*deff[0]+.25*(hv[3]-av[3])+
                        .15*(hv[4]-av[4])+.10*(hv[5]-av[5])+.10*deff[2])
            edge_off=float((1-cur_weight)*(hp[0]-ap[0])+cur_weight*custom_off)
            edge_def=float((1-cur_weight)*(hp[1]-ap[1])+cur_weight*custom_def)
            if not np.isfinite(edge_off) or not np.isfinite(edge_def):
                continue
            magnitude=min(edge_off,edge_def)
            midrange=(out[gid]["group"]=="P4" and .50<=magnitude<.75)
            qualifies=edge_off>EPS and edge_def>EPS and not midrange
            out[gid].update({
               "status":"ok","off_edge":edge_off,"def_edge":edge_def,
               "magnitude":magnitude,"qualifies":bool(qualifies),
               "reason":(
                   "P4 magnitude 0.50–0.74 excluded." if midrange else
                   "Home has stronger pregame offense and defense." if qualifies else
                   "Home lacks both positive pregame rating advantages."
               )
            })
    except (ValueError,KeyError,TypeError,IndexError,AttributeError,OverflowError,
            FloatingPointError,ZeroDivisionError):
        return out
    return out
