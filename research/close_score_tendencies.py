"""Leakage-safe research only: competitive-script pass/run tendency.

Input CSVs:
plays: game_id,season,week,kickoff_utc,offense_team,defense_team,
       home_team,away_team,quarter,clock_seconds,pre_snap_home_score,
       pre_snap_away_score,play_type (run/pass),offense_epa
games: game_id,season,week,kickoff_utc,home_team,away_team,
       home_score,away_score,baseline_home_prob

Only *previously kicked-off AND completed* games feed team profiles.
No production forecasts are modified. Games in the same kickoff batch
are evaluated without borrowing information from each other.
"""
import argparse
import json
import numpy as np
import pandas as pd

REQUIRED_PLAYS = ["game_id","season","week","kickoff_utc","offense_team","defense_team",
                  "home_team","away_team","quarter","clock_seconds",
                  "pre_snap_home_score","pre_snap_away_score","play_type","offense_epa"]
REQUIRED_GAMES = ["game_id","season","week","kickoff_utc","home_team","away_team",
                  "home_score","away_score","baseline_home_prob"]


def prepare(plays, games):
    for name, df, cols in [("plays",plays,REQUIRED_PLAYS),("games",games,REQUIRED_GAMES)]:
        missing = sorted(set(cols)-set(df.columns))
        if missing:
            raise ValueError(f"{name}: missing {missing}")
    p = plays.copy()
    g = games.copy()
    p["kickoff_utc"] = pd.to_datetime(p.kickoff_utc,utc=True,errors="raise")
    g["kickoff_utc"] = pd.to_datetime(g.kickoff_utc,utc=True,errors="raise")
    for col in ["quarter","clock_seconds","pre_snap_home_score","pre_snap_away_score","offense_epa"]:
        p[col] = pd.to_numeric(p[col],errors="coerce")
    for col in ["home_score","away_score","baseline_home_prob"]:
        g[col] = pd.to_numeric(g[col],errors="coerce")
    p["play_type"] = p.play_type.astype(str).str.lower()
    p = p[p.play_type.isin(["run","pass"]) & p.quarter.between(1,4)].copy()
    if p[["quarter","clock_seconds","pre_snap_home_score","pre_snap_away_score"]].isna().any().any():
        raise ValueError("Missing clock or pre-snap scores; cannot infer from final scores")
    p["competitive"] = (
        (p.pre_snap_home_score-p.pre_snap_away_score).abs().le(8)
        & p.quarter.le(3)
        & ~((p.quarter.eq(2)) & (p.clock_seconds.le(120)))
    )
    # Remove games with unverified finals. Excludes FCS by requiring supplied
    # FBS-only schedules and asserting team identities against supplied games.
    if g.game_id.duplicated().any():
        raise ValueError("Duplicate game IDs in outcomes")
    if not g.baseline_home_prob.between(0.001,0.999).all():
        raise ValueError("Baseline probabilities must be pregame values between 0.001 and 0.999")
    return p,g.sort_values(["kickoff_utc","game_id"])


def profiles(history, scope):
    x=history if scope=="overall" else history[history.competitive]
    # Offense EPA by play type; defense EPA allowed by play type. Pass frequency
    # excludes sacks and scrambles only if source is already classified that way.
    teams={}
    for t in set(x.offense_team)|set(x.defense_team):
        a=x[x.offense_team.eq(t)]
        d=x[x.defense_team.eq(t)]
        if len(a)<30 or len(d)<30:
            continue
        pr=(a.play_type=="pass").mean()
        epa_o=a.groupby("play_type").offense_epa.mean()
        epa_d=d.groupby("play_type").offense_epa.mean()
        if not all(k in epa_o.index and k in epa_d.index for k in ["pass","run"]):
            continue
        teams[t]={"pass_rate":float(pr),"count":int(len(a)),
                  "off_pass":float(epa_o["pass"]),"off_run":float(epa_o["run"]),
                  "def_pass":float(epa_d["pass"]),"def_run":float(epa_d["run"])}
    return teams


def predict(base, home, away, strength=0.75):
    # A team's preferred attack weighted against opponent EPA allowed,
    # centered on 50/50 to isolate the effect of tendency. Difference
    # between home and away matchup expected EPA, added in log-odds space.
    def advantage(o,d):
        w=o["pass_rate"]
        return w*(o["off_pass"]-d["def_pass"])+(1-w)*(o["off_run"]-d["def_run"])
    delta=advantage(home,away)-advantage(away,home)
    return float(1/(1+np.exp(-(np.log(base/(1-base))+strength*delta))))


def run(plays,games):
    p,g=prepare(plays,games)
    rows=[]
    valid_results=g[g.home_score.notna() & g.away_score.notna()].copy()
    # Use kickoff timestamp as proxy ONLY when known final before target kickoff:
    # An actual final_at_utc column is required for strict point-in-time eligibility.
    if "final_at_utc" not in games.columns:
        raise ValueError("games must include final_at_utc (required for no future leakage)")
    valid_results["final_at_utc"]=pd.to_datetime(
        valid_results["final_at_utc"],utc=True,errors="coerce")
    for _,game in g.iterrows():
        if pd.isna(game.home_score) or pd.isna(game.away_score) or game.home_score==game.away_score:
            continue
        past_ids=set(valid_results.loc[
            valid_results.final_at_utc.lt(game.kickoff_utc) &
            valid_results.season.le(game.season),"game_id"])
        history=p[p.game_id.isin(past_ids)]
        overall=profiles(history,"overall")
        competitive=profiles(history,"competitive")
        h,a=game.home_team,game.away_team
        if not all(team in overall and team in competitive for team in [h,a]):
            continue  # Matched sample prevents cherry-picked comparisons
        home_gap=abs(overall[h]["pass_rate"]-competitive[h]["pass_rate"])
        away_gap=abs(overall[a]["pass_rate"]-competitive[a]["pass_rate"])
        max_gap=max(home_gap,away_gap)
        y=int(game.home_score>game.away_score)
        base=float(game.baseline_home_prob)
        po=predict(base,overall[h],overall[a])
        pc=predict(base,competitive[h],competitive[a])
        # Reliability-based smoothing: small competitive samples borrow
        # strength from all plays. Same weight rule frozen for every game.
        hybrid={}
        for team in (h,a):
            n=competitive[team]["count"]
            alpha=n/(n+150)
            hybrid[team]={key:alpha*competitive[team][key]+(1-alpha)*overall[team][key]
                          for key in ("pass_rate","off_pass","off_run","def_pass","def_run")}
        ph=predict(base,hybrid[h],hybrid[a])
        rows.append({"game_id":game.game_id,"season":game.season,"week":game.week,
                     "home_team":h,"away_team":a,"actual_home_win":y,
                     "baseline":base,"overall":po,"competitive":pc,"hybrid":ph,
                     "home_gap_pp":round(home_gap*100,2),"away_gap_pp":round(away_gap*100,2),
                     "max_gap_pp":round(max_gap*100,2),
                     "gap_group":"10pp+" if max_gap>=.10 else "under10pp",
                     "home_competitive_plays":competitive[h]["count"],
                     "away_competitive_plays":competitive[a]["count"],
                     "home_pass_overall":overall[h]["pass_rate"],
                     "home_pass_competitive":competitive[h]["pass_rate"],
                     "away_pass_overall":overall[a]["pass_rate"],
                     "away_pass_competitive":competitive[a]["pass_rate"]})
    detail=pd.DataFrame(rows)
    if detail.empty:
        return detail,pd.DataFrame()
    summary=[]
    for name in ["baseline","overall","competitive","hybrid"]:
        x=detail[name].to_numpy()
        y=detail.actual_home_win.to_numpy()
        summary.append({"candidate":name,"games":len(detail),
                        "correct":int(((x>=.5)==y).sum()),
                        "accuracy":float(((x>=.5)==y).mean()),
                        "brier":float(np.mean((x-y)**2)),
                        "log_loss":float(np.mean(-(y*np.log(x)+(1-y)*np.log(1-x))))})
    return detail,pd.DataFrame(summary)

def subgroup_report(detail):
    """Paired comparisons; all models scored on the exact same games."""
    if detail.empty:
        return pd.DataFrame()
    output=[]
    for group,x in [("all",detail),
                    ("10pp+",detail[detail.max_gap_pp>=10]),
                    ("under10pp",detail[detail.max_gap_pp<10]),
                    ("15pp+",detail[detail.max_gap_pp>=15]),
                    ("20pp+",detail[detail.max_gap_pp>=20])]:
        y=x.actual_home_win.to_numpy()
        for candidate in ["baseline","overall","competitive","hybrid"]:
            p=x[candidate].to_numpy()
            output.append({"gap_group":group,"candidate":candidate,"games":len(x),
                           "wins":int(((p>=.5)==y).sum()) if len(x) else 0,
                           "accuracy":float(((p>=.5)==y).mean()) if len(x) else np.nan,
                           "brier":float(np.mean((p-y)**2)) if len(x) else np.nan})
    return pd.DataFrame(output)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--plays",required=True)
    parser.add_argument("--games",required=True)
    parser.add_argument("--out",default="close_score_results")
    args=parser.parse_args()
    detail,summary=run(pd.read_csv(args.plays),pd.read_csv(args.games))
    detail.to_csv(args.out+"_games.csv",index=False)
    summary.to_csv(args.out+"_summary.csv",index=False)
    subgroup_report(detail).to_csv(args.out+"_subgroups.csv",index=False)
    print(summary.to_string(index=False) if not summary.empty else "No eligible paired games")


if __name__=="__main__":
    main()
