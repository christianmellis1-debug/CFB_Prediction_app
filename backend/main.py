from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from model import predict_week

ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title="CFB Predictor API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _read_csv_url(url: str, timeout: int = 60) -> pd.DataFrame:
    with urlopen(url, timeout=timeout) as response:
        return pd.read_csv(BytesIO(response.read()), low_memory=False)


@lru_cache(maxsize=8)
def schedule(season: int) -> pd.DataFrame:
    local = ROOT / f"schedule{season}.csv"
    if local.exists():
        frame = pd.read_csv(local, low_memory=False)
    else:
        frame = _read_csv_url(f"https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{season}.csv")
    frame = frame[pd.to_numeric(frame["season"], errors="coerce") == season].copy()
    if "season_type" in frame:
        frame = frame[frame["season_type"].astype(str).str.lower() == "regular"]
    for col in ("home_division", "away_division"):
        if col in frame:
            frame = frame[frame[col].astype(str).str.lower() == "fbs"]
    for col in ("week", "home_id", "away_id", "home_points", "away_points"):
        if col in frame:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    for col in ("completed", "neutral_site"):
        if col in frame:
            frame[col] = frame[col].astype(str).str.lower().isin(("true", "t", "1", "1.0", "yes", "y"))
    return frame.dropna(subset=["week", "home_id", "away_id"]).sort_values("start_date", kind="stable")


@lru_cache(maxsize=8)
def summary(year: int) -> pd.DataFrame:
    local = ROOT / f"summary{year}.csv"
    if local.exists():
        frame = pd.read_csv(local, low_memory=False)
    else:
        frame = _read_csv_url("https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"
                              f"cfb_team_summaries_weekly/cfb_team_summaries_weekly_{year}.csv")
    return frame[pd.to_numeric(frame["season"], errors="coerce") == year].copy()


def logo(team_id) -> str:
    try:
        return f"https://a.espncdn.com/i/teamlogos/ncaa/500/{int(team_id)}.png"
    except (TypeError, ValueError):
        return ""


def moneyline(value):
    if value is None:
        return "Unavailable"
    raw = str(value).strip().replace("−", "-")
    if raw.upper() in {"EVEN", "EV", "EVS"}:
        return "+100"
    try:
        number = float(raw)
        return f"{int(number):+d}" if math.isfinite(number) and abs(number) >= 100 and number.is_integer() else "Unavailable"
    except (ValueError, TypeError):
        return "Unavailable"


def parse_quotes(payload: dict) -> dict:
    quotes = {}
    for event in payload.get("events", []):
        event_quotes = {}
        for competition in event.get("competitions", []):
            sides = {c.get("homeAway"): str(c.get("team", {}).get("id", "")) for c in competition.get("competitors", [])}
            for odds in competition.get("odds", []):
                provider = str(odds.get("provider", {}).get("name", "")).strip()
                if not provider:
                    continue
                prices = {}
                for side in ("home", "away"):
                    market = odds.get("moneyline", {}).get(side, {})
                    value = (market.get("close") or {}).get("odds") if "close" in market else odds.get(side + "TeamOdds", {}).get("moneyLine")
                    prices[side] = moneyline(value)
                if prices["home"] != "Unavailable" or prices["away"] != "Unavailable":
                    event_quotes[provider] = {"home_id": sides.get("home", ""), "away_id": sides.get("away", ""), **prices}
        if event_quotes:
            quotes[str(event.get("id"))] = event_quotes
    return quotes


@lru_cache(maxsize=16)
def odds(date_range: str) -> dict:
    url = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?" + urlencode({"dates": date_range, "groups": 80, "limit": 1000})
    with urlopen(url, timeout=20) as response:
        return {"quotes": parse_quotes(json.load(response)), "retrieved": datetime.now(timezone.utc).isoformat()}


def json_rows(frame: pd.DataFrame):
    return json.loads(frame.where(pd.notna(frame), None).to_json(orient="records"))


def _implied(line: str):
    try:
        n = float(str(line).replace("+", ""))
        return 100 / (n + 100) if n > 0 else -n / (-n + 100)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def attach_market_context(predicted: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    result = predicted.copy()
    for col, default in (("Away ML", "Unavailable"), ("Home ML", "Unavailable"), ("ML Source", "Unavailable"), ("Odds Type", "Not offered / unavailable")):
        result[col] = default
    if "start_date" not in games or games.empty:
        return result
    dates = pd.to_datetime(games["start_date"], errors="coerce", utc=True).dropna()
    if dates.empty:
        return result
    period = dates.min().strftime("%Y%m%d") + "-" + dates.max().strftime("%Y%m%d")
    try:
        quote_events = odds(period).get("quotes", {})
    except Exception:
        quote_events = {}
    for idx, game in games.iterrows():
        event_quotes = quote_events.get(str(game.get("game_id")), {})
        if not event_quotes:
            continue
        valid = [q for name, q in event_quotes.items() if isinstance(q, dict)
                 and str(q.get("home_id")) == str(int(game.home_id))
                 and str(q.get("away_id")) == str(int(game.away_id))]
        if not valid:
            continue
        named = [(name, q) for name, q in event_quotes.items() if isinstance(q, dict)
                 and str(q.get("home_id")) == str(int(game.home_id))
                 and str(q.get("away_id")) == str(int(game.away_id))]
        dk = next(((name, q) for name, q in named if name.lower().replace(" ", "") == "draftkings"), None)
        provider, quote = dk or named[0]
        match = (result["Home Team"] == game.home_team) & (result["Away Team"] == game.away_team)
        result.loc[match, "Away ML"] = quote.get("away", "Unavailable")
        result.loc[match, "Home ML"] = quote.get("home", "Unavailable")
        result.loc[match, "ML Source"] = provider
        result.loc[match, "Odds Type"] = "Archived line" if bool(game.get("completed", False)) else "Latest available line"
    result["Bet Line"] = result.apply(lambda r: r["Home ML"] if r["Predicted Side"] == "Home" else r["Away ML"], axis=1)
    result["Market Implied %"] = result["Bet Line"].map(_implied)
    result["Model Edge"] = result["Confidence"] - result["Market Implied %"]
    result["Expected Value"] = result.apply(lambda r: (
        r["Confidence"] * (float(str(r["Bet Line"]).replace("+", "")) / 100) - (1-r["Confidence"]))
        if str(r["Bet Line"]).startswith("+") and pd.notna(r["Market Implied %"]) else (
        r["Confidence"] * (100 / abs(float(str(r["Bet Line"])))) - (1-r["Confidence"]))
        if pd.notna(r["Market Implied %"]) else None, axis=1)
    result["Bet Signal"] = "Pass"
    usable = result["Market Implied %"].notna()
    result.loc[usable & (result["Confidence"] >= .70) & (result["Model Edge"] >= .03) & (result["Expected Value"] > 0), "Bet Signal"] = "Strong value"
    result.loc[usable & (result["Bet Signal"] == "Pass") & (result["Confidence"] >= .60) & (result["Model Edge"] >= .02) & (result["Expected Value"] > 0), "Bet Signal"] = "Value"
    result.loc[~usable, "Bet Signal"] = "No line"
    return result


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "cfb-predictor-api", "model": "V1.4"}


@app.get("/api/weeks")
def weeks(season: int = Query(..., ge=2001, le=2100)):
    try:
        frame = schedule(season)
        return {"season": season, "weeks": sorted(frame["week"].astype(int).unique().tolist())}
    except Exception as exc:
        raise HTTPException(502, f"Unable to load schedule: {exc}") from exc


@app.get("/api/predictions")
def predictions(season: int = Query(..., ge=2001, le=2100), week: int = Query(..., ge=1, le=30)):
    try:
        games = schedule(season)
        current, prior = summary(season), summary(season - 1)
        predicted = predict_week(current, prior, games, week, include_completed=True)
        if predicted.empty:
            return {"season": season, "week": week, "retrieved": datetime.now(timezone.utc).isoformat(), "games": []}
        selected = games[pd.to_numeric(games.week, errors="coerce") == week]
        predicted["Status"] = "Awaiting final"
        predicted["Actual Winner"] = "—"
        predicted["Final Score"] = "—"
        for idx, row in selected.iterrows():
            match = (predicted["Home Team"] == row.home_team) & (predicted["Away Team"] == row.away_team)
            complete = bool(row.get("completed", False))
            if complete and pd.notna(row.home_points) and pd.notna(row.away_points):
                predicted.loc[match, "Status"] = "Final"
                predicted.loc[match, "Actual Winner"] = row.home_team if row.home_points > row.away_points else row.away_team if row.away_points > row.home_points else "Tie"
                predicted.loc[match, "Final Score"] = f"{row.away_team} {row.away_points:g} – {row.home_team} {row.home_points:g}"
            predicted.loc[match, "Away Logo"] = logo(row.away_id)
            predicted.loc[match, "Home Logo"] = logo(row.home_id)
            predicted.loc[match, "Game ID"] = row.get("game_id")
        predicted = attach_market_context(predicted, selected)
        return {"season": season, "week": week, "model": "V1.4", "retrieved": datetime.now(timezone.utc).isoformat(), "games": json_rows(predicted)}
    except Exception as exc:
        raise HTTPException(502, f"Unable to generate predictions: {exc}") from exc
