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
OUTPUT = ROOT / "research" / "value_shortlist_roi_2026" / "week6_preview.json"
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


def read_current_espn_quotes(game_id, fn):
    try:
        payload = json.loads(fetch(
            "https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event=" + str(game_id),
            timeout=22,
        ))
        header = payload.get("header", {})
        if str(header.get("id")) != str(game_id):
            raise ValueError("ESPN game ID mismatch")
        competitions = []
        for competition in header.get("competitions", []):
            entry = dict(competition)
            entry["odds"] = payload.get("pickcenter", []) or competition.get("odds", [])
            competitions.append(entry)
        quotes = fn["parse_draftkings"]({"events":[{"id": str(game_id), "competitions": competitions}]}).get(str(game_id), {})
        return str(game_id), quotes, None if quotes else "No sportsbook prices"
    except Exception as exc:
        return str(game_id), {}, type(exc).__name__ + ": " + str(exc)[:160]

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
    week = 6
    asof = datetime.now(timezone.utc)
    games = schedule[schedule.week.eq(week)].copy()
    kickoff_utc = pd.to_datetime(games["start_date"], utc=True, errors="coerce")
    eligible_games = games[~games["completed"] & kickoff_utc.gt(pd.Timestamp(asof))].copy()
    print("WEEK", week, "FBS total", len(games), "unplayed", len(eligible_games), "asof", asof.isoformat(), flush=True)
    augmented, derived = fn["augment_missing_summaries"](data["current"], data["prior"], schedule, week)
    predictions = fn["predict_all_games"](augmented, data["prior"], schedule, week)
    predictions = fn["attach_results"](predictions, games)
    records = [game for _, game in eligible_games.iterrows()]
    with ThreadPoolExecutor(max_workers=12) as pool:
        fetched = list(pool.map(lambda game: read_current_espn_quotes(int(game.game_id), fn), records))
    quotes, errors = {}, {}
    for gid, found, error in fetched:
        if found:
            quotes[gid] = found
        elif error:
            errors[gid] = error
    print("PRICE COVERAGE", len(quotes), "of", len(eligible_games), "errors", len(errors), flush=True)
    predictions = fn["add_betting_value"](fn["attach_odds"](predictions, games, quotes))
    profiles = build_waterfall_profiles(schedule, data["boxes"], week)
    wanted_ids = {int(game.game_id) for _,game in eligible_games.iterrows()}
    weather_ids = [gid for gid in weather_tier_candidate_ids(predictions, schedule, profiles) if gid in wanted_ids]
    print("WEATHER CANDIDATES",len(weather_ids),flush=True)
    try:
        weather = build_weather_context(schedule, week, weather_ids) if weather_ids else {}
    except Exception as exc:
        print("WEATHER ERROR", type(exc).__name__, str(exc)[:100], flush=True)
        weather = {}
    annotated = model.add_waterfall_value(
        predictions, schedule, data["boxes"], week, weather_checks=weather,
        published_summary=data["current"],
    )
    selected = annotated[annotated["Value Selected"]].sort_values("Value Rank").copy()
    selected = selected[pd.to_numeric(selected["Game ID"], errors="coerce").isin(wanted_ids)]
    picks=[]
    for _, row in selected.iterrows():
        price = fn["format_moneyline"](row.get("Value Price"))
        match = eligible_games[eligible_games.game_id.eq(int(row["Game ID"]))]
        kickoff = str(match.iloc[0]["start_date"]) if not match.empty else ""
        picks.append({
            "week": week, "game_id": int(row["Game ID"]),
            "matchup": str(row["Away Team"]) + " at " + str(row["Home Team"]),
            "tier": str(row["Value Tier"]), "stage": int(row["Value Stage"]),
            "market": str(row["Value Market"]), "selection": str(row["Value Pick"]),
            "line": str(row["Value Line"]), "american_odds": price,
            "sportsbook": str(row["Value Source"]), "status": str(row["Status"]),
            "kickoff": kickoff, "is_priced": price != "Unavailable",
        })
    flat = [p for p in picks if p["stage"] != 4 and p["is_priced"]]
    tier4 = [p for p in picks if p["stage"] == 4 and p["is_priced"]]
    missing_prices=[p for p in picks if not p["is_priced"]]
    groups=[]
    for start in range(0,len(tier4)-2,3):
        triple=tier4[start:start+3]
        decimal_odds=1.0
        for p in triple:
            n=int(p["american_odds"])
            decimal_odds *= (1+n/100) if n>0 else (1+100/abs(n))
        groups.append({
            "legs": triple,
            "decimal_odds": decimal_odds,
            "american_odds_approx": round_money((decimal_odds-1)*100) if decimal_odds>=2 else -round_money(100/(decimal_odds-1)),
        })
    unused_tier4=tier4[3*len(groups):]
    stakes={}
    for stake in (10,20,100):
        bets=[]
        for p in flat:
            n=int(p["american_odds"])
            profit=round_money(stake*n/100 if n>0 else stake*100/abs(n))
            bets.append({"type":"single", "stage":p["stage"],"selection":p["selection"],"risk":stake,"profit_if_win":profit})
        for group in groups:
            bets.append({"type":"3-leg-parlay","selection":" + ".join(x["selection"] for x in group["legs"]),"risk":stake,"profit_if_win":round_money(stake*(group["decimal_odds"]-1))})
        risk=round_money(sum(x["risk"] for x in bets))
        profit=round_money(sum(x["profit_if_win"] for x in bets))
        stakes[str(stake)]={
            "tickets":len(bets),"straight_tickets":len(flat),"three_leg_parlays":len(groups),
            "total_at_risk":risk,"profit_if_all_win":profit,
            "total_return_if_all_win":round_money(risk+profit),
            "all_win_roi_percent":round_money(100*profit/risk) if risk else None,
            "lose_all_net":-risk,"ticket_payouts":bets,
        }
    out={
        "season":SEASON,"week":week,"asof_utc":asof.isoformat(),
        "method":"Current 2026 week 6 pregame Value Shortlist reconstructed from production selection rules and ESPN prices. Upcoming FBS games only. Hypothetical all-win returns, not probability-weighted expected ROI. Flat stakes on straight picks in tiers 1,2,3,5; each nonoverlapping same-week triple from tier 4 gets one parlay; unused tier4 games not bet.",
        "future_games":len(eligible_games),"all_week_games":len(games),
        "quote_events":len(quotes),"price_errors":errors,
        "weather_candidate_ids":weather_ids,
        "weather_unavailable":[str(i) for i in weather_ids if weather.get(str(i),{}).get("status") not in ("ok","indoor")],
        "value_picks":picks,"individual_tickets":flat,"parlays":groups,
        "unpaired_tier4":unused_tier4,"unpriced":missing_prices,
        "stake_scenarios":stakes,
    }
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(out,indent=2,allow_nan=False)+"\n")
    print("SUMMARY",json.dumps({
        "picks":len(picks),"flat":len(flat),"tier4":len(tier4),"parlays":len(groups),
        "unpaired":len(unused_tier4),"unpriced":len(missing_prices),
        "stake_scenarios":{k:{a:b for a,b in v.items() if a!="ticket_payouts"} for k,v in stakes.items()},
        "weather_missing":len(out["weather_unavailable"]),
    }),flush=True)

if __name__=="__main__":
    main()
