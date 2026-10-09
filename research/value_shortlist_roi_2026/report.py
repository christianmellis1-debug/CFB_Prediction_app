"""Reconstruct the current official Value Shortlist for 2026 weeks 3-5, $100 flat stakes.
Research output only; never alters production app or the value model.
"""
import ast
import json
import math
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import model_v1_5 as model
from matchup_advantages import (
    normalize_fbs_schedule, build_waterfall_profiles, weather_tier_candidate_ids,
)
from weather_context import build_weather_context

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "research" / "value_shortlist_roi_2026" / "results.json"
SEASON = 2026
WEEKS = (3, 4, 5)
BASE = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"
URLS = {
    "schedule": "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_2026.csv",
    "current": BASE + "cfb_team_summaries_weekly/cfb_team_summaries_weekly_2026.csv",
    "prior": BASE + "cfb_team_summaries_weekly/cfb_team_summaries_weekly_2025.csv",
    "boxes": BASE + "espn_cfb_team_box/team_box_2026.csv",
}

def fetch(url, timeout=75):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 SaturdayForecast-Research"})
    with urlopen(request, timeout=timeout) as response:
        return response.read()

def read_csv(item):
    data = fetch(URLS[item])
    print("INPUT", item, len(data), flush=True)
    return pd.read_csv(BytesIO(data), low_memory=False)

def app_functions():
    source = (ROOT / "app.py").read_text()
    tree = ast.parse(source)
    names = (
        "augment_missing_summaries", "predict_all_games", "attach_results",
        "format_moneyline", "format_spread", "parse_draftkings",
        "parse_archived_summary", "attach_odds", "add_betting_value",
    )
    namespace = {
        "pd": pd, "np": np, "math": math, "predict_week": model.predict_week,
    }
    for name in names:
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        node.decorator_list = []
        exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), namespace)
    return namespace

def round_money(value):
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

def read_espn_quotes(game_id, fn):
    try:
        payload = json.loads(fetch(
            "https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event=" + str(game_id),
            timeout=20,
        ))
        data = fn["parse_archived_summary"](payload, str(game_id))
        if data:
            return str(game_id), data, None
        return str(game_id), {}, "No archived sportsbook odds"
    except Exception as exc:
        return str(game_id), {}, "ESPN archive unavailable: " + str(exc)[:100]

def local_week5_quote(game, fn):
    path = ROOT / "research" / "six_advantage_odds_2026_week5" / (str(int(game.game_id)) + ".json")
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        header = {"id": str(int(game.game_id)), "competitions": [{
            "status": {"type": {"completed": True}},
            "competitors": [
                {"homeAway": "home", "team": {"id": str(int(game.home_id))}},
                {"homeAway": "away", "team": {"id": str(int(game.away_id))}},
            ],
        }]}
        return fn["parse_archived_summary"](
            {"header": header, "pickcenter": data.get("pickcenter", [])},
            str(int(game.game_id)),
        )
    except Exception:
        return {}

def profit_100(result, price):
    if result == "Push":
        return 0.0
    if result == "Incorrect":
        return -100.0
    if result != "Correct":
        return None
    try:
        line = int(float(str(price).replace("+", "").replace("−", "-")))
    except (ValueError, TypeError):
        return None
    if abs(line) < 100:
        return None
    return round_money(100.0 * (line / 100.0 if line > 0 else 100.0 / abs(line)))

def main():
    fn = app_functions()
    with ThreadPoolExecutor(max_workers=4) as pool:
        data = dict(zip(URLS, pool.map(read_csv, URLS)))
    schedule = data["schedule"]
    schedule = schedule[pd.to_numeric(schedule.season, errors="coerce").eq(SEASON)]
    schedule = schedule[schedule.season_type.astype(str).str.lower().eq("regular")]
    schedule = normalize_fbs_schedule(schedule)
    for col in ("week", "home_id", "away_id", "game_id", "home_points", "away_points"):
        schedule[col] = pd.to_numeric(schedule[col], errors="coerce")
    schedule = schedule.dropna(subset=["week", "home_id", "away_id", "game_id"])
    schedule = schedule[schedule.week.ge(1)].sort_values("start_date", kind="stable")
    schedule["completed"] = schedule.completed.astype(str).str.lower().isin(["true", "t", "1", "1.0", "yes", "y"])
    for item, yr in (("current", 2026), ("prior", 2025)):
        data[item] = data[item][pd.to_numeric(data[item].season, errors="coerce").eq(yr)].copy()

    archive_errors = {}
    out = []
    weekly = []
    for week in WEEKS:
        games = schedule[schedule.week.eq(week)].copy()
        print("WEEK", week, "games", len(games), flush=True)
        augmented, derived = fn["augment_missing_summaries"](
            data["current"], data["prior"], schedule, week
        )
        predictions = fn["predict_all_games"](augmented, data["prior"], schedule, week)
        predictions = fn["attach_results"](predictions, games)
        records = [game for _, game in games.iterrows()]
        with ThreadPoolExecutor(max_workers=12) as pool:
            fetched = list(pool.map(
                lambda game: read_espn_quotes(int(game.game_id), fn), records
            ))
        quote_map = {}
        failures = {}
        for gid, record, error in fetched:
            if record:
                quote_map[gid] = record
            elif error:
                failures[gid] = error
        if week == 5:
            for game in records:
                gid = str(int(game.game_id))
                if gid not in quote_map:
                    recovered = local_week5_quote(game, fn)
                    if recovered:
                        quote_map[gid] = recovered
                        failures.pop(gid, None)
        archive_errors[str(week)] = failures
        print("ODDS", week, len(quote_map), "/", len(games),
              "missing:", len(failures), flush=True)
        predictions = fn["add_betting_value"](fn["attach_odds"](predictions, games, quote_map))
        profiles = build_waterfall_profiles(schedule, data["boxes"], week)
        weather_ids = weather_tier_candidate_ids(predictions, schedule, profiles)
        print("WEATHER candidates", week, len(weather_ids), flush=True)
        try:
            weather = build_weather_context(schedule, week, weather_ids) if weather_ids else {}
        except Exception as exc:
            print("WEATHER ERROR", week, str(exc), flush=True)
            weather = {}
        weather_missing = [
            str(gid) for gid in weather_ids
            if weather.get(str(gid), {}).get("status") not in ("ok", "indoor")
        ]
        annotated = model.add_waterfall_value(
            predictions, schedule, data["boxes"], week, weather_checks=weather,
            published_summary=data["current"],
        )
        selected = annotated[annotated["Value Selected"]].sort_values("Value Rank")
        for _, row in selected.iterrows():
            price = fn["format_moneyline"](row.get("Value Price"))
            result = str(row.get("Value Result"))
            amount = profit_100(result, price) if price != "Unavailable" else None
            out.append({
                "week": week,
                "game_id": int(row["Game ID"]),
                "matchup": str(row["Away Team"]) + " at " + str(row["Home Team"]),
                "tier": str(row["Value Tier"]),
                "market": str(row["Value Market"]),
                "selection": str(row["Value Pick"]),
                "line": str(row["Value Line"]),
                "american_odds": price,
                "sportsbook": str(row["Value Source"]),
                "result": result,
                "net_profit_usd": amount,
                "final_score": str(row["Final Score"]),
            })
        rows = [x for x in out if x["week"] == week]
        settled = [x for x in rows if x["result"] in ("Correct", "Incorrect", "Push")]
        priced = [x for x in settled if x["net_profit_usd"] is not None]
        stake = 100 * len(priced)
        net = round_money(sum(x["net_profit_usd"] for x in priced))
        entry = {
            "week": week, "selected": len(rows), "settled": len(settled),
            "wins": sum(x["result"] == "Correct" for x in settled),
            "losses": sum(x["result"] == "Incorrect" for x in settled),
            "pushes": sum(x["result"] == "Push" for x in settled),
            "priced_and_settled": len(priced),
            "missing_price_or_result": len(rows) - len(priced),
            "total_staked_usd": stake,
            "net_profit_usd": net,
            "total_returned_usd": round_money(stake + net),
            "roi_percent": round_money(100 * net / stake) if stake else None,
            "weather_candidates": len(weather_ids),
            "weather_unavailable": weather_missing,
            "game_coverage": len(games),
            "provider_coverage": len(quote_map),
        }
        weekly.append(entry)
        print("RESULT", json.dumps(entry, sort_keys=True), flush=True)

    total_bets = sum(w["priced_and_settled"] for w in weekly)
    total_stake = total_bets * 100
    total_net = round_money(sum(w["net_profit_usd"] for w in weekly))
    output = {
        "method": "Retrospective reconstruction using current Value Shortlist rules, not an immutable pregame betting card; American odds from available ESPN archived sportsbook snapshots, 100-dollar flat stakes, no fees, reinvestment or parlays.",
        "season": SEASON, "weeks": list(WEEKS),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "weekly": weekly,
        "total": {
            "selected": sum(w["selected"] for w in weekly),
            "wins": sum(w["wins"] for w in weekly),
            "losses": sum(w["losses"] for w in weekly),
            "pushes": sum(w["pushes"] for w in weekly),
            "priced_and_settled": total_bets,
            "missing_price_or_result": sum(w["missing_price_or_result"] for w in weekly),
            "staked_usd": total_stake, "net_profit_usd": total_net,
            "returned_usd": round_money(total_stake + total_net),
            "roi_percent": round_money(100 * total_net / total_stake) if total_stake else None,
        },
        "picks": out,
        "archive_errors": archive_errors,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print("TOTAL", json.dumps(output["total"], sort_keys=True), flush=True)

if __name__ == "__main__":
    main()
