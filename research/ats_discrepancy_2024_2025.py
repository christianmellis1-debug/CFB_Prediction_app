"""Historical FBS pregame ATS gap analysis — research only (no app/model changes)."""
from io import BytesIO
from urllib.request import urlopen
import pandas as pd

SCHEDULE_URL = "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{year}.csv"
ODDS_URL = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_betting/betting_{year}.csv"

def fetch_csv(url):
    with urlopen(url, timeout=65) as r:
        return pd.read_csv(BytesIO(r.read()), low_memory=False)

def truth(s):
    return s.astype(str).str.strip().str.lower().isin(["true", "t", "1", "yes", "y", "1.0"])

def season_data(year):
    schedule = fetch_csv(SCHEDULE_URL.format(year=year))
    odds = fetch_csv(ODDS_URL.format(year=year))
    print("DIAGNOSTIC", year, "schedule", schedule.shape, "odds", odds.shape)
    print("DIAGNOSTIC", year, "odds columns", list(odds.columns))
    print("DIAGNOSTIC", year, "schedule columns", list(schedule.columns))
    needed = ["game_id", "week", "season_type", "home_division", "away_division", "completed", "home_id", "away_id", "home_team", "away_team", "home_points", "away_points"]
    missing = set(needed) - set(schedule.columns)
    if missing:
        raise ValueError(f"Schedule missing: {missing}")
    needed_odds = {"game_id", "home_team_spread", "game_spread_available"}
    if not needed_odds.issubset(odds.columns):
        raise ValueError(f"Odds missing: {needed_odds - set(odds.columns)}")
    schedule = schedule.copy()
    schedule = schedule[
        schedule["season_type"].astype(str).str.lower().eq("regular")
        & schedule["home_division"].astype(str).str.lower().eq("fbs") & schedule["away_division"].astype(str).str.lower().eq("fbs") & truth(schedule["completed"])
    ].copy()
    for c in ["game_id","week","home_id","away_id","home_points","away_points"]:
        schedule[c] = pd.to_numeric(schedule[c], errors="coerce")
    schedule = schedule.dropna(subset=["game_id","week","home_id","away_id","home_points","away_points"]).drop_duplicates("game_id")
    odds = odds.copy()
    odds["game_id"] = pd.to_numeric(odds["game_id"],errors="coerce")
    odds["home_team_spread"] = pd.to_numeric(odds["home_team_spread"], errors="coerce")
    odds = odds[truth(odds["game_spread_available"]) & odds["home_team_spread"].notna()].copy()
    if "odds_source" in odds:
        odds = odds[~odds["odds_source"].astype(str).str.lower().isin(["default","injected"])]
    odds = odds.drop_duplicates("game_id")
    schedule = schedule.merge(odds[["game_id","home_team_spread"]], how="left", on="game_id", validate="one_to_one")
    # Sort by official season/week; every pregame record is frozen before its week.
    schedule = schedule.sort_values(["week", "game_id"])
    print("DIAGNOSTIC", year, "completed_fbs_fbs",len(schedule),"verified_spreads",schedule.home_team_spread.notna().sum(), "week_range",schedule.week.min(), schedule.week.max())
    return schedule

def run(season, games):
    record = {}
    rows = []
    for week, slate in games.groupby("week",sort=True):
        for _, g in slate.iterrows():
            hid, aid = int(g.home_id), int(g.away_id)
            home = record.get(hid,(0,0,0))
            away = record.get(aid,(0,0,0))
            hnet = home[0]-home[1]
            anet = away[0]-away[1]
            netgap = abs(hnet-anet)
            wingap = abs(home[0]-away[0])
            hrate = home[0] / (home[0]+home[1]) if (home[0]+home[1]) else None
            arate = away[0] / (away[0]+away[1]) if (away[0]+away[1]) else None
            # Explicitly skip exact ties; there is no higher-ATS team.
            if hnet != anet:
                better_home = hnet > anet
                spread = g.home_team_spread
                diff = float(g.home_points)-float(g.away_points)
                if pd.notna(spread):
                    covermargin = diff + float(spread)
                    cover = 1 if (covermargin > 1e-7) == better_home and abs(covermargin)>1e-7 else (0 if abs(covermargin)>1e-7 else -1)
                else:
                    cover = None
                rows.append({
                    "season":season,"week":int(week),"game_id":int(g.game_id),
                    "matchup":f"{g.away_team} at {g.home_team}",
                    "favored_by_ats":g.home_team if better_home else g.away_team,
                    "favored_pre_ATS":str(home if better_home else away),
                    "other_pre_ATS":str(away if better_home else home),
                    "net_gap":netgap,"win_gap":wingap,
                    "home_team":str(g.home_team),"away_team":str(g.away_team),
                    "home_points":int(g.home_points),"away_points":int(g.away_points),
                    "stronger_is_home":bool(better_home),
                    "stronger_line":(-float(spread) if not better_home else float(spread)) if pd.notna(spread) else None,
                    "min_lined_games":min(sum(home),sum(away)),
                    "better_ats_won_su":int((diff>0)==better_home) if diff != 0 else -1,
                    "better_ats_covered":cover,
                })
        # Settle completed matchups from the week only AFTER every game in
        # the week's pregame values has been recorded.
        for _,g in slate.iterrows():
            if pd.isna(g.home_team_spread):
                continue
            hid, aid = int(g.home_id), int(g.away_id)
            diff = float(g.home_points)-float(g.away_points)+float(g.home_team_spread)
            for team_id, result in [(hid, diff), (aid, -diff)]:
                w,l,p=record.get(team_id,(0,0,0))
                if result > 1e-7: w+=1
                elif result < -1e-7: l+=1
                else: p+=1
                record[team_id]=(w,l,p)
    return rows

def summarize(rows, gap_field, min_sample=0):
    frame=pd.DataFrame(rows)
    frame=frame[frame.min_lined_games>=min_sample]
    print(f"TABLE metric={gap_field} minimum_prior_lined_games_each_team={min_sample} total_comparisons={len(frame)}")
    for yr in [2024,2025,"combined"]:
        pool=frame if yr=="combined" else frame[frame.season.eq(yr)]
        for label,lo,hi in [("4",4,4),("5",5,5),("6",6,6),("7+",7,1000),("4+",4,1000)]:
            subset=pool[(pool[gap_field]>=lo)&(pool[gap_field]<=hi)]
            su_w=(subset.better_ats_won_su==1).sum()
            su_l=(subset.better_ats_won_su==0).sum()
            su_t=(subset.better_ats_won_su==-1).sum()
            cov_w=(subset.better_ats_covered==1).sum()
            cov_l=(subset.better_ats_covered==0).sum()
            cov_p=(subset.better_ats_covered==-1).sum()
            miss=subset.better_ats_covered.isna().sum()
            print(f"ROW,{yr},{label},{len(subset)},SU={su_w}-{su_l}-{su_t},ATS={cov_w}-{cov_l}-{cov_p},missing_lines={miss},SU%={su_w/(su_w+su_l)*100:.1f}" if su_w+su_l else f"ROW,{yr},{label},{len(subset)},SU={su_w}-{su_l}-{su_t},ATS={cov_w}-{cov_l}-{cov_p},missing_lines={miss},SU%=NA")
    if gap_field == "net_gap" and not min_sample:
        chosen=frame[frame[gap_field]>=7].sort_values(["season","week","matchup"])
        for _,g in chosen.iterrows():
            print(f"GAME,{g.season},week={g.week},gap={g.net_gap},SU={g.better_ats_won_su},ATS={g.better_ats_covered},prior={g.favored_pre_ATS} vs {g.other_pre_ATS},{g.favored_by_ats} vs {g.matchup}")

if __name__=="__main__":
    rows = []
    for year in [2024,2025]:
        rows.extend(run(year,season_data(year)))
    print("ALL_ROWS",len(rows))
    for r in sorted((r for r in rows if r["season"]==2025 and r["net_gap"]>=7),key=lambda r:(r["week"],r["game_id"])):
        line=r["stronger_line"]
        print("DETAIL2025|"+ "|".join([
            str(r["week"]),str(r["net_gap"]),str(r["favored_by_ats"]),
            r["home_team"],r["away_team"],str(r["home_points"]),str(r["away_points"]),
            f"{line:+g}" if line is not None else "N/A",
            "W" if r["better_ats_won_su"]==1 else "L",
            "W" if r["better_ats_covered"]==1 else "L" if r["better_ats_covered"]==0 else "P",
            r["favored_pre_ATS"],r["other_pre_ATS"],str(r["game_id"])
        ]))
    summarize(rows,"net_gap")
    summarize(rows,"win_gap")
    summarize(rows,"net_gap",min_sample=3)
