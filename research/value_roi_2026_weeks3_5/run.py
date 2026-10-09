"""Reconstruct 2026 Weeks 3–5 official Value Picks, report $100 flat-stake ROI.

Exploratory retrospective reconstruction, not an immutable pregame pick record.
Uses the same production prediction, market parsing, five-stage selection,
weather qualification and ROI accounting routines as Saturday Forecast.
"""
import ast
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO
import json
import math
from pathlib import Path
import sys
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import model_v1_5 as model
from model_v1_5 import add_waterfall_value
from matchup_advantages import (build_waterfall_profiles, weather_tier_candidate_ids,
                                normalize_fbs_schedule)
from weather_context import build_weather_context
from value_roi import value_roi_detail, roi_summary

URLS = {
    "schedule": "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_2026.csv",
    "current": "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_2026.csv",
    "prior": "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/cfb_team_summaries_weekly/cfb_team_summaries_weekly_2025.csv",
    "box": "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_2026.csv",
}


def load_feed(item):
    name, url = item
    req = Request(url, headers={"User-Agent": "SaturdayForecast-ValueROI/1.0"})
    with urlopen(req, timeout=90) as response:
        content = response.read()
    print("FEED", name, "bytes", len(content), flush=True)
    return name, pd.read_csv(BytesIO(content), low_memory=False)


# Extract just production pure functions without executing Streamlit app UI.
tree = ast.parse((ROOT / "app.py").read_text())
wanted = {
    "augment_missing_summaries", "predict_all_games", "attach_results",
    "format_moneyline", "format_spread", "parse_draftkings",
    "parse_archived_summary", "attach_odds", "add_betting_value",
}
defs = [f for f in tree.body if isinstance(f, ast.FunctionDef) and f.name in wanted]
assert {f.name for f in defs} == wanted
for function in defs:
    function.decorator_list = []
ns = {"pd": pd, "np": np, "math": math, "predict_week": model.predict_week}
exec(compile(ast.Module(body=defs, type_ignores=[]), "official_app_helpers", "exec"), ns)


def fetch_event(game):
    gid = str(int(game["game_id"]))
    url = ("https://site.api.espn.com/apis/site/v2/sports/football/"
           "college-football/summary?event=" + gid)
    try:
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as response:
            payload = json.load(response)
        quote = ns["parse_archived_summary"](payload, gid)
        return gid, quote, None
    except Exception as e:
        return gid, {}, str(e)


feeds = dict(ThreadPoolExecutor(max_workers=4).map(load_feed, URLS.items()))
schedule = normalize_fbs_schedule(feeds["schedule"]).copy()
schedule = schedule[
    pd.to_numeric(schedule["season"], errors="coerce").eq(2026)
    & schedule["season_type"].astype(str).str.lower().eq("regular")
].copy()
for col in ("week", "home_id", "away_id", "game_id", "home_points", "away_points"):
    schedule[col] = pd.to_numeric(schedule[col], errors="coerce")
for col in ("completed", "neutral_site"):
    schedule[col] = schedule[col].astype(str).str.lower().isin(["true", "t", "1", "1.0", "yes"])
schedule = schedule.sort_values("start_date", kind="stable")
schedule = schedule.dropna(subset=["week", "game_id", "home_id", "away_id"])
assert schedule["game_id"].is_unique, "ambiguous game ids"
print("FBS SCHEDULE", len(schedule), flush=True)

all_games = schedule[schedule["week"].isin([3, 4, 5])]
with ThreadPoolExecutor(max_workers=8) as pool:
    event_quotes = list(pool.map(fetch_event, [g for _, g in all_games.iterrows()]))
quotes = {gid: markets for gid, markets, error in event_quotes if markets}
lookup_errors = {gid: error for gid, markets, error in event_quotes if error}
print("ESPN ARCHIVED QUOTES", len(quotes), "of", len(all_games), "failed", len(lookup_errors), flush=True)

results = []
weather_stats = {}
for week in (3, 4, 5):
    game_week = schedule[schedule["week"].eq(week)].copy()
    current, _ = ns["augment_missing_summaries"](
        feeds["current"], feeds["prior"], schedule, week)
    picks = ns["predict_all_games"](current, feeds["prior"], schedule, week)
    picks = ns["attach_results"](picks, game_week)
    picks = ns["add_betting_value"](ns["attach_odds"](picks, game_week, quotes))
    profiles = build_waterfall_profiles(schedule, feeds["box"], week)
    candidates = weather_tier_candidate_ids(picks, schedule, profiles)
    weather = build_weather_context(schedule, week, tuple(candidates)) if candidates else {}
    weather_stats[str(week)] = {
        "tier2_candidates": len(candidates),
        "verified_weather": sum(v.get("status") == "ok" for v in weather.values()),
        "missing_weather": sum(v.get("status") == "missing" for v in weather.values()),
    }
    selected = add_waterfall_value(
        picks, schedule, feeds["box"], week,
        weather_checks=weather, published_summary=feeds["current"])
    selected = selected[selected["Value Selected"]].copy()
    print("WEEK", week, "official picks", len(selected),
          "results", selected["Value Result"].value_counts().to_dict(), flush=True)
    results.append(selected)

detail = value_roi_detail(pd.concat(results, ignore_index=True), stake=100, weeks=[3, 4, 5])
weekly = roi_summary(detail, "Week")
tier = roi_summary(detail, "Tier")
total = roi_summary(detail)
out = {
    "reconstructed_at_utc": datetime.now(timezone.utc).isoformat(),
    "experiment": "Exploratory retrospective reconstruction, not pre-kickoff frozen picks",
    "odds_provenance": "ESPN archived per-event summary (availability and book prices vary)",
    "stake_per_pick_usd": 100,
    "total": total.to_dict(orient="records"),
    "weekly": weekly.to_dict(orient="records"),
    "by_tier": tier.to_dict(orient="records"),
    "weather_coverage": weather_stats,
    "games_with_archived_odds": len(quotes),
    "historical_games": len(all_games),
    "event_lookup_errors": lookup_errors,
    "missing_price_count": int(detail["ROI Status"].eq("Missing price").sum()),
}
print("FINAL_ROI_SUMMARY_JSON=" + json.dumps(out, allow_nan=False, default=str), flush=True)
print("PER_PICK_DETAILS_CSV_START", flush=True)
print(detail.to_csv(index=False), flush=True)
print("PER_PICK_DETAILS_CSV_END", flush=True)
