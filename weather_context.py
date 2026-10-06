"""Pregame weather context for Value Picks.

Uses ESPN venue metadata plus Open-Meteo. Weather is descriptive input only;
selection logic remains in matchup_advantages.select_waterfall.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor
import json
import math

import pandas as pd

THUNDER_CODES = {95, 96, 99}
PRECIP_MM = 1.0
SUSTAINED_WIND_MPH = 20.0
GUST_MPH = 30.0


def _json(base, params=None, timeout=20):
    url = base + (("?" + urlencode(params, doseq=True)) if params else "")
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 cfb-predictor-weather"})
    with urlopen(req, timeout=timeout) as response:
        return json.load(response)


def _truthy(value):
    return str(value).strip().lower() in {"true", "t", "1", "1.0", "yes", "y"}


def _venue(venue_id):
    return _json(
        f"https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/venues/{int(venue_id)}",
        {"lang": "en", "region": "us"},
    )


def _geocode(address):
    city = str(address.get("city") or "").strip()
    state = str(address.get("state") or "").strip()
    country = str(address.get("country") or "").strip()
    if not city:
        return None
    query = ", ".join(x for x in (city, state if country in {"USA", "United States", "US"} else country) if x)
    params = {"name": query, "count": 5, "format": "json", "language": "en"}
    if country in {"USA", "United States", "US"}:
        params["countryCode"] = "US"
    results = (_json("https://geocoding-api.open-meteo.com/v1/search", params).get("results") or [])
    if not results:
        return None
    chosen = results[0]
    if state:
        match = next((r for r in results if str(r.get("admin1", "")).casefold() == state.casefold()), None)
        if match:
            chosen = match
    lat, lon = chosen.get("latitude"), chosen.get("longitude")
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


def _hourly_weather(lat, lon, kickoff):
    kickoff = pd.to_datetime(kickoff, utc=True, errors="coerce")
    if pd.isna(kickoff):
        return None
    start_date = kickoff.date()
    end_date = (kickoff + pd.Timedelta(hours=5)).date()
    today = datetime.now(timezone.utc).date()
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "timezone": "UTC",
        "wind_speed_unit": "mph",
        "hourly": "precipitation,snowfall,weather_code,wind_speed_10m,wind_gusts_10m",
    }
    if start_date < today:
        base = "https://historical-forecast-api.open-meteo.com/v1/forecast"
    else:
        base = "https://api.open-meteo.com/v1/forecast"
    payload = _json(base, params)
    hourly = payload.get("hourly") or {}
    times = pd.to_datetime(hourly.get("time", []), utc=True, errors="coerce")
    frame = pd.DataFrame({
        "time": times,
        "precipitation": pd.to_numeric(pd.Series(hourly.get("precipitation", [])), errors="coerce"),
        "snowfall": pd.to_numeric(pd.Series(hourly.get("snowfall", [])), errors="coerce"),
        "weather_code": pd.to_numeric(pd.Series(hourly.get("weather_code", [])), errors="coerce"),
        "wind_speed_10m": pd.to_numeric(pd.Series(hourly.get("wind_speed_10m", [])), errors="coerce"),
        "wind_gusts_10m": pd.to_numeric(pd.Series(hourly.get("wind_gusts_10m", [])), errors="coerce"),
    }).dropna(subset=["time"])
    start = kickoff.floor("h")
    window = frame[(frame.time >= start) & (frame.time <= start + pd.Timedelta(hours=4))]
    if window.empty:
        return None
    precip = float(window.precipitation.fillna(0).sum())
    snow = float(window.snowfall.fillna(0).sum())
    wind = float(window.wind_speed_10m.max()) if window.wind_speed_10m.notna().any() else math.nan
    gust = float(window.wind_gusts_10m.max()) if window.wind_gusts_10m.notna().any() else math.nan
    codes = {int(x) for x in window.weather_code.dropna().tolist()}
    wet = precip >= PRECIP_MM or snow > 0 or bool(codes & THUNDER_CODES)
    windy = (math.isfinite(wind) and wind >= SUSTAINED_WIND_MPH) or (math.isfinite(gust) and gust >= GUST_MPH)
    if wet and windy:
        weather_type = "Wet/snow + wind"
    elif wet:
        weather_type = "Wet/snow only"
    elif windy:
        weather_type = "Wind only"
    else:
        weather_type = "Ordinary"
    return {
        "status": "ok",
        "inclement": bool(wet or windy),
        "weather_type": weather_type,
        "precip_mm": precip,
        "snowfall": snow,
        "max_wind_mph": wind,
        "max_gust_mph": gust,
        "weather_codes": sorted(codes),
    }


def build_weather_context(schedule, week, game_ids=None):
    """Return game-id keyed weather context for selected candidate games.

    Indoor, neutral, unresolved-venue, and unavailable-weather games fail closed.
    game_ids can restrict network work to football/spread candidates only.
    """
    if schedule is None or schedule.empty or "game_id" not in schedule:
        return {}
    games = schedule.copy()
    games["week"] = pd.to_numeric(games.get("week"), errors="coerce")
    games = games[games.week.eq(int(week))]
    wanted = {str(int(x)) for x in (game_ids or []) if str(x).strip()}
    if wanted:
        numeric_ids = pd.to_numeric(games["game_id"], errors="coerce")
        games = games[numeric_ids.map(lambda x: str(int(x)) if pd.notna(x) else "").isin(wanted)]

    def one(game):
        try:
            gid = str(int(game["game_id"]))
        except (TypeError, ValueError, OverflowError):
            return None, None
        if _truthy(game.get("neutral_site", False)):
            return gid, {"status": "neutral", "inclement": False, "reason": "Neutral-site game."}
        try:
            venue_id = int(float(game.get("venue_id")))
        except (TypeError, ValueError, OverflowError):
            return gid, {"status": "missing", "inclement": False, "reason": "Venue ID unavailable."}
        try:
            venue = _venue(venue_id)
        except Exception:
            return gid, {"status": "missing", "inclement": False, "reason": "Venue metadata unavailable."}
        if venue.get("indoor") is True:
            return gid, {"status": "indoor", "inclement": False, "reason": "Indoor venue."}
        if venue.get("indoor") is not False:
            return gid, {"status": "missing", "inclement": False, "reason": "Venue roof status unavailable."}
        address = venue.get("address") or {}
        try:
            coords = _geocode(address)
        except Exception:
            coords = None
        if not coords:
            return gid, {"status": "missing", "inclement": False, "reason": "Venue location unavailable."}
        kickoff = pd.to_datetime(game.get("start_date"), utc=True, errors="coerce")
        if pd.isna(kickoff):
            return gid, {"status": "missing", "inclement": False, "reason": "Kickoff time unavailable."}
        try:
            weather = _hourly_weather(coords[0], coords[1], kickoff)
        except Exception:
            weather = None
        if not weather:
            return gid, {"status": "missing", "inclement": False, "reason": "Weather unavailable."}
        return gid, weather

    out = {}
    records = [row for _, row in games.iterrows()]
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(records)))) as pool:
        for gid, weather in pool.map(one, records):
            if gid is not None:
                out[gid] = weather
    return out

