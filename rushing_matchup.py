"""Pregame FBS rushing offense vs opposing rush-defense matchup observations.

Informational only: no changes to V1.5, primary Test C or six betting tiers.
Uses only previously completed FBS-vs-FBS box scores before the target week
and kickoff, then peer-ranks raw rushing yards per carry.
"""
from html import escape
import math
from collections import defaultdict
import numpy as np
import pandas as pd
from matchup_advantages import normalize_fbs_schedule

QUARTILE = 0.25
MIN_PEER_TEAMS = 12

def build_rushing_matchup_insights(schedule, boxes, week):
    out = {}
    if not {"season","season_type","game_id","week","home_id","away_id",
            "start_date","completed","home_points","away_points"}.issubset(schedule):
        return out
    if not {"game_id","team_id","rushingYards","rushingAttempts"}.issubset(boxes):
        return out
    s = normalize_fbs_schedule(schedule).copy()
    for col in ("week","game_id","home_id","away_id","season","home_points","away_points"):
        s[col] = pd.to_numeric(s[col], errors="coerce")
    s["start"] = pd.to_datetime(s.start_date, utc=True, errors="coerce")
    s = s.dropna(subset=["week","game_id","home_id","away_id","season"])
    target = s[s.week.eq(int(week)) & s.season_type.astype(str).str.lower().eq("regular")]
    if target.empty:
        return out
    for game in target.itertuples():
        out[str(int(game.game_id))] = {"status":"unavailable"}
    b = boxes[["game_id","team_id","rushingYards","rushingAttempts"]].copy()
    for col in b:
        b[col] = pd.to_numeric(b[col], errors="coerce")
    dup = b.duplicated(["game_id","team_id"],keep=False)
    valid = (~dup) & np.isfinite(b[["game_id","team_id","rushingYards","rushingAttempts"]]).all(axis=1)
    valid &= b.rushingAttempts.gt(0) & b.rushingAttempts.mod(1).eq(0)
    lookup = b[valid].set_index(["game_id","team_id"])
    completed = s.completed.astype(str).str.lower().isin(["true","t","1","yes","y","1.0"])
    histories = s[
       s.season_type.astype(str).str.lower().eq("regular") &
       completed & s.week.lt(int(week)) &
       s.home_points.notna() & s.away_points.notna() &
       s.start.notna()
    ]
    per_season = {}
    for season in target.season.dropna().unique():
        season = int(season)
        current = target[target.season.eq(season)]
        kickoff = current.start.min()
        if pd.isna(kickoff):
            continue
        past = histories[histories.season.eq(season) & histories.start.lt(kickoff)]
        totals = defaultdict(lambda: np.zeros(5, dtype=float))
        for old in past.itertuples():
            if not math.isfinite(float(old.game_id)):
                continue
            hk=(old.game_id,old.home_id);ak=(old.game_id,old.away_id)
            if hk not in lookup.index or ak not in lookup.index:
                continue
            own,opponent=lookup.loc[hk],lookup.loc[ak]
            if not all(math.isfinite(float(x)) for x in (
                own.rushingYards,own.rushingAttempts,opponent.rushingYards,opponent.rushingAttempts)):
                continue
            totals[int(old.home_id)] += [
                own.rushingYards,own.rushingAttempts,
                opponent.rushingYards,opponent.rushingAttempts,1.
            ]
            totals[int(old.away_id)] += [
                opponent.rushingYards,opponent.rushingAttempts,
                own.rushingYards,own.rushingAttempts,1.
            ]
        profiles={}
        for tid,v in totals.items():
            if v[1]>0 and v[3]>0:
                profiles[tid]={
                    "off_ypc":float(v[0]/v[1]),
                    "allowed_ypc":float(v[2]/v[3]),
                    "prior_games":int(v[4]),
                }
        if len(profiles)<MIN_PEER_TEAMS:
            continue
        ids=list(profiles)
        off_pct=pd.Series([profiles[t]["off_ypc"] for t in ids]).rank(method="average",pct=True)
        def_pct=pd.Series([profiles[t]["allowed_ypc"] for t in ids]).rank(method="average",pct=True)
        for i,tid in enumerate(ids):
            profiles[tid]["off_pct"]=float(off_pct.iloc[i])
            profiles[tid]["def_pct"]=float(def_pct.iloc[i])
        per_season[season] = (profiles,len(profiles))
        for game in current.itertuples():
            gid=str(int(game.game_id))
            h=profiles.get(int(game.home_id));a=profiles.get(int(game.away_id))
            if not (h and a):
                continue
            out[gid] = {
               "status":"ok",
               "home":h,"away":a,"peers":len(profiles),
               # Low percentile defensive yards allowed is good defense.
               "home_disadvantaged":h["off_pct"]<=QUARTILE and a["def_pct"]<=QUARTILE,
               "away_disadvantaged":a["off_pct"]<=QUARTILE and h["def_pct"]<=QUARTILE,
            }
    return out


def rushing_matchup_html(info, home_name, away_name):
    if not info or info.get("status")!="ok":
        return ""
    h,a=info["home"],info["away"]
    hbad=bool(info.get("home_disadvantaged"));abad=bool(info.get("away_disadvantaged"))
    label = " · weak run attack vs strong run defense" if hbad or abad else ""
    descriptions=[]
    if hbad:
        descriptions.append(f"<strong>{escape(str(home_name))}</strong> ranks in the bottom quarter of rushing YPC, while <strong>{escape(str(away_name))}</strong> ranks in the strongest quarter of yards per carry allowed.")
    if abad:
        descriptions.append(f"<strong>{escape(str(away_name))}</strong> ranks in the bottom quarter of rushing YPC, while <strong>{escape(str(home_name))}</strong> ranks in the strongest quarter of yards per carry allowed.")
    if not descriptions:
        descriptions.append("No bottom-quarter rushing offense versus top-quarter run-defense pairing was identified.")
    def row(name,p):
        return (
            f"<li><strong>{escape(str(name))}</strong>: "
            f"{p['off_ypc']:.2f} rushing yards per carry on offense; "
            f"{p['allowed_ypc']:.2f} yards per carry allowed on defense; "
            f"{p['prior_games']} prior FBS game(s).</li>"
        )
    return (
        '<details class="card-details"><summary>Rushing matchup'
        +escape(label)+'</summary>'
        +''.join(f"<p>{x}</p>" for x in descriptions)
        +'<ul>'+row(home_name,h)+row(away_name,a)+'</ul>'
        +f'<p>Pregame FBS-only rushing rates, ranked against {int(info["peers"])} teams with valid prior-game samples. '
        'This is a descriptive matchup flag, not an automatic reduction to the winner probability; historical testing did not validate a stand-alone penalty. Betting tiers remain independent.</p>'
        '</details>'
    )
