"""Research-only opponent-adjusted margin test for Tier 1, 2024–2026.

Walk-forward features: a team's prior FBS scores and pregame Elo ratings of each
previous opponent, through weeks strictly before the predicted game.
2024 -> 2025 and (2024+2025) -> 2026 are untouched season holdouts.
2026 official pregame archive is evaluated separately from reconstructing earlier picks.
No production files, tiers, or selection rules are altered.
"""
import json
import math
import unittest
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
from matchup_advantages import build_advantages, assess

ROOT = Path(__file__).resolve().parents[1]
YEARS = (2024, 2025, 2026)
URLS = {
    "schedule": "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{year}.csv",
    "box": "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_{year}.csv",
    "market": "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_betting/betting_{year}.csv",
}
P4 = {"ACC", "Big Ten", "Big 12", "SEC"}
G6 = {"American Athletic", "Conference USA", "Mid-American", "Mountain West", "Sun Belt", "Pac-12"}
# Fixed feature specification, not optimized on Tier 1 outcomes:
BASE_POINTS = 28.0
ELO_POINTS_PER_RATING = 0.035
HOME_POINTS = 3.0
PRIOR_GAMES_SHRINK = 3.0
RIDGE_PENALTY = 10.0
VALUE_THRESHOLDS = (0, 2, 3, 5)
FEATURES = ("elo", "raw", "opponent")

def fetch_one(item):
    name, url = item
    with urlopen(Request(url, headers={"User-Agent":"SaturdayForecast-OpponentResearch/1.0"}), timeout=105) as f:
        raw = f.read()
    print("SOURCE", name, "bytes", len(raw), flush=True)
    return name, pd.read_csv(BytesIO(raw), low_memory=False)

def is_true(x):
    return x.astype(str).str.lower().str.strip().isin(("true","t","1","1.0","yes","y"))

def group(conference, team):
    if str(team).strip().casefold() == "notre dame":
        return "P4"
    if conference in P4:
        return "P4"
    if conference in G6:
        return "G6"
    return None

def history_features(history):
    # Both participants need at least two prior verified FBS games. Sparse history
    # is shrunk rather than treated as reliable full-season efficiency.
    n = len(history)
    if n < 2:
        return None
    off, defense, adj_off, adj_def = [], [], [], []
    for x in history:
        home = x["home"]
        pf, pa = x["pf"], x["pa"]
        expected_pf_raw = BASE_POINTS + 0.5 * HOME_POINTS * home
        expected_pa_raw = BASE_POINTS - 0.5 * HOME_POINTS * home
        expected_pf_adj = expected_pf_raw + 0.5 * ELO_POINTS_PER_RATING * (x["elo"] - x["opponent_elo"])
        expected_pa_adj = expected_pa_raw - 0.5 * ELO_POINTS_PER_RATING * (x["elo"] - x["opponent_elo"])
        off.append(pf - expected_pf_raw)
        defense.append(expected_pa_raw - pa)
        adj_off.append(pf - expected_pf_adj)
        adj_def.append(expected_pa_adj - pa)
    shrink = n / (n + PRIOR_GAMES_SHRINK)
    return (
        shrink * float(np.mean(off)), shrink * float(np.mean(defense)),
        shrink * float(np.mean(adj_off)), shrink * float(np.mean(adj_def)),
    )

def feature_games(schedule):
    # Build week-scoped histories. Games from the current week cannot enter any
    # prediction in that week even if played on a Thursday before Saturday.
    history = {}
    rows = []
    dates = sorted(int(w) for w in schedule.week.dropna().unique())
    for week in dates:
        current = schedule[schedule.week.eq(week)]
        for _, game in current.iterrows():
            if game.home_group != game.away_group or game.home_group is None or game.neutral_site:
                continue
            if (not game.completed or not np.isfinite(game.home_points) or not np.isfinite(game.away_points)
                    or not np.isfinite(game.home_pregame_elo) or not np.isfinite(game.away_pregame_elo)):
                continue
            h = history_features(history.get(int(game.home_id), []))
            a = history_features(history.get(int(game.away_id), []))
            if h is None or a is None:
                continue
            rows.append({
                "year": int(game.season), "week": week, "event_id": int(game.game_id),
                "home": str(game.home_team), "away": str(game.away_team),
                "elo_diff": float(game.home_pregame_elo - game.away_pregame_elo),
                "raw_off_diff": h[0] - a[0], "raw_def_diff": h[1] - a[1],
                "opp_off_diff": h[2] - a[2], "opp_def_diff": h[3] - a[3],
                "home_margin": float(game.home_points - game.away_points),
            })
        # Update *after* predicting every game in the entire week.
        for _, game in current.iterrows():
            if (not game.completed or not np.isfinite(game.home_points) or not np.isfinite(game.away_points)
                    or not np.isfinite(game.home_pregame_elo) or not np.isfinite(game.away_pregame_elo)):
                continue
            home, away = int(game.home_id), int(game.away_id)
            history.setdefault(home, []).append({
                "home": 1, "pf": float(game.home_points), "pa": float(game.away_points),
                "elo": float(game.home_pregame_elo), "opponent_elo":float(game.away_pregame_elo),
            })
            history.setdefault(away, []).append({
                "home": -1, "pf": float(game.away_points), "pa": float(game.home_points),
                "elo": float(game.away_pregame_elo), "opponent_elo":float(game.home_pregame_elo),
            })
    return pd.DataFrame(rows)

def fit_ridge(frame, model):
    columns = ["elo_diff"] if model=="elo" else (
        ["elo_diff","raw_off_diff","raw_def_diff"] if model=="raw"
        else ["elo_diff","opp_off_diff","opp_def_diff"])
    X = frame[columns].to_numpy(dtype=float)
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd < 1e-8] = 1.
    X = (X-mu)/sd
    X = np.column_stack([np.ones(len(X)), X])
    y = frame.home_margin.to_numpy(dtype=float)
    penalty = np.diag([0.]+[RIDGE_PENALTY]*(X.shape[1]-1))
    coefficients = np.linalg.solve(X.T @ X + penalty, X.T @ y)
    return {"columns": columns, "mean":mu, "sd":sd, "coef":coefficients}

def predict(model, frame):
    X = frame[model["columns"]].to_numpy(dtype=float)
    X = (X - model["mean"])/model["sd"]
    return model["coef"][0] + X @ model["coef"][1:]

def numeric(v):
    return pd.to_numeric(v, errors="coerce")

def prepare_schedule(schedule):
    s = schedule[
        schedule.season_type.astype(str).str.lower().eq("regular")
        & schedule.home_division.astype(str).str.lower().eq("fbs")
        & schedule.away_division.astype(str).str.lower().eq("fbs")
    ].copy()
    for c in ("season", "week", "game_id", "home_id", "away_id",
              "home_points", "away_points", "home_pregame_elo", "away_pregame_elo"):
        s[c] = numeric(s[c])
    s = s.dropna(subset=["season","week","game_id","home_id","away_id"])
    s["completed"] = is_true(s.completed)
    s["neutral_site"] = is_true(s.neutral_site)
    s["home_group"] = [group(c,t) for c,t in zip(s.home_conference,s.home_team)]
    s["away_group"] = [group(c,t) for c,t in zip(s.away_conference,s.away_team)]
    if s.game_id.duplicated().any():
        raise AssertionError("Ambiguous FBS game ID")
    return s

def reconstruct_tier1(schedule, boxes, market):
    quotes = market.copy()
    quotes["game_id"] = numeric(quotes.game_id)
    quotes["home_team_spread"] = numeric(quotes.home_team_spread)
    quotes = quotes[is_true(quotes.game_spread_available)&quotes.game_id.notna()
                    & quotes.home_team_spread.notna()]
    if "odds_source" in quotes:
        quotes = quotes[~quotes.odds_source.astype(str).str.lower().eq("default")]
    duplicates = set(quotes.loc[quotes.duplicated("game_id",keep=False),"game_id"].astype(int))
    quotes = quotes[~quotes.game_id.isin(duplicates)]
    lines = dict(zip(quotes.game_id.astype(int),quotes.home_team_spread))
    picks=[]; six=0
    for week in sorted(int(w) for w in schedule.week.dropna().unique()):
        if week < 2:
            continue
        checks = build_advantages(schedule, boxes, week)
        games=schedule[schedule.week.eq(week)&schedule.completed&schedule.home_points.notna()
                       &schedule.away_points.notna()]
        for _,g in games.iterrows():
            rec=checks.get(str(int(g.game_id)),{})
            if g.neutral_site or rec.get("status")!="ok":
                continue
            a=assess(rec,"home")
            if a is None or a["count"] != 5:
                continue
            six+=1
            spread=lines.get(int(g.game_id))
            if spread is None:
                continue
            cov=float(g.home_points-g.away_points+spread)
            picks.append({
                "event_id":int(g.game_id), "year":int(g.season), "week":week,
                "home":str(g.home_team), "away":str(g.away_team),
                "spread":float(spread), "ats_margin":cov,
                "ats_result":"Win" if cov>1e-7 else "Loss" if cov<-1e-7 else "Push",
            })
    return pd.DataFrame(picks),{"six_qualifiers":six, "with_spread":len(picks),
                                "missing_spread":six-len(picks)}

def grade(rows, pred_column=None, threshold=None):
    if pred_column is not None:
        rows=rows[rows[pred_column]+rows.spread>threshold]
    if rows.empty:
        return {"n":0,"wins":0,"losses":0,"pushes":0,"ats_pct":None,"avg_cover_margin":None}
    w=int(rows.ats_result.eq("Win").sum());l=int(rows.ats_result.eq("Loss").sum())
    p=int(rows.ats_result.eq("Push").sum())
    return {"n":len(rows),"wins":w,"losses":l,"pushes":p,
            "ats_pct":round(100*w/(w+l),2) if w+l else None,
            "avg_cover_margin":round(float(rows.ats_margin.mean()),2)}

def metrics(frame,col):
    diff=frame[col]-frame.home_margin
    return {"n":len(diff),"mae":round(float(diff.abs().mean()),3),
            "rmse":round(float(np.sqrt((diff**2).mean())),3),
            "bias":round(float(diff.mean()),3)}

def run():
    with ThreadPoolExecutor(max_workers=9) as executor:
        raw=list(executor.map(fetch_one, [
            (f"{year}_{kind}",template.format(year=year))
            for year in YEARS for kind,template in URLS.items()
        ]))
    feeds=dict(raw)
    schedules={}; features={}; original={}; coverage={}
    for year in YEARS:
        s=prepare_schedule(feeds[f"{year}_schedule"])
        schedules[year]=s
        features[year]=feature_games(s)
        original[year],coverage[year]=reconstruct_tier1(s,feeds[f"{year}_box"],feeds[f"{year}_market"])
        print("YEAR_PREP",year,"features",len(features[year]),"tier1",coverage[year],flush=True)
        if features[year].empty:
            raise AssertionError("Missing full-season historical feature coverage "+str(year))
    f24=features[2024];f25=features[2025];f26=features[2026]
    training={
        "2025":{m:fit_ridge(f24,m) for m in FEATURES},
        "2026":{m:fit_ridge(pd.concat([f24,f25],ignore_index=True),m) for m in FEATURES},
    }
    out={"specification":{
        "years":YEARS,"features":"prior-week FBS PF/PA, home correction, past opponent pregame Elo",
        "base_points":BASE_POINTS,"elo_points_per_rating":ELO_POINTS_PER_RATING,
        "home_points":HOME_POINTS,"prior_games_shrink":PRIOR_GAMES_SHRINK,
        "ridge_penalty":RIDGE_PENALTY,"thresholds":VALUE_THRESHOLDS,
        "note":"Historical odds may be revised; no prices, no return or ROI claim. No future games in history."
    },"coverage":coverage,"season_tests":{},"tier1":{},"locked_week7":{}}
    for season in (2025,2026):
        f=features[season].copy()
        for m in FEATURES:
            f["pred_"+m]=predict(training[str(season)][m],f)
        out["season_tests"][season]={
            "training_seasons":[2024] if season==2025 else [2024,2025],
            "margin_metrics":{m:metrics(f,"pred_"+m) for m in FEATURES},
            "coefficients":{m:{"intercept":round(float(training[str(season)][m]["coef"][0]),3),
                                  "features":dict(zip(training[str(season)][m]["columns"],
                                          [round(float(v/sd),4) for v,sd in zip(training[str(season)][m]["coef"][1:],
                                                                training[str(season)][m]["sd"])]))}
                            for m in FEATURES},
        }
        selections=original[season].merge(
            f[["event_id"]+["pred_"+m for m in FEATURES]],on="event_id",how="left",validate="one_to_one")
        selections=selections.dropna(subset=["pred_"+m for m in FEATURES])
        out["tier1"][season]={
            "all_6of6":grade(selections),
            "eligible_margin_features":len(selections),
            "selection_coverage":len(selections)/len(original[season]) if len(original[season]) else 0,
            "filter_tests":{
                m:{str(th):grade(selections,"pred_"+m,th) for th in VALUE_THRESHOLDS}
                for m in FEATURES
            },
        }
        if season==2026:
            week7=selections[selections.week.eq(7)].copy()
            archive=json.loads((ROOT/"data/value_archive_2026.json").read_text())
            locked={int(k):v for k,v in archive["snapshots"].items()
                    if v.get("week")==7 and v.get("selected") is True and v.get("Value Stage")==1}
            locked_results=archive.get("results",{})
            frozen=week7[week7.event_id.isin(locked)].copy()
            frozen["spread"]=frozen.event_id.map(lambda gid: float(locked[int(gid)]["Value Line"]))
            frozen["ats_margin"]=frozen.event_id.map(
                lambda gid: float(locked_results[str(int(gid))]["home_score"])
                            -float(locked_results[str(int(gid))]["away_score"])
                            +float(locked[int(gid)]["Value Line"]))
            frozen["ats_result"]=frozen.ats_margin.map(lambda z:"Win" if z>1e-7 else "Loss" if z<-1e-7 else "Push")
            out["locked_week7"]={
                "count_locked":len(locked),"count_matched":len(frozen),
                "all":grade(frozen),
                "filter_tests":{
                    m:{str(th):grade(frozen,"pred_"+m,th) for th in VALUE_THRESHOLDS}
                    for m in FEATURES
                },
                "games":[{
                    "home":row.home, "away":row.away,
                    "line":float(row.spread), "outcome":row.ats_result,
                    "edge_elo":round(float(row.pred_elo+row.spread),1),
                    "edge_raw":round(float(row.pred_raw+row.spread),1),
                    "edge_opponent":round(float(row.pred_opponent+row.spread),1),
                } for _,row in frozen.iterrows()]
            }
    print("OPPONENT_ADJUSTMENT_REPORT="+json.dumps(out,allow_nan=False),flush=True)
    return out

class TestOpponentAdjustmentHistorical(unittest.TestCase):
    def test_opponent_adjustment_historical(self):
        result=run()
        self.assertEqual(result["locked_week7"]["count_locked"],10)
        self.assertEqual(result["locked_week7"]["count_matched"],10)
        self.assertGreater(result["tier1"][2025]["eligible_margin_features"],30)

if __name__=="__main__":
    unittest.main(verbosity=2)
