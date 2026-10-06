"""Game-window weather context for matchup cards and Value Picks.

Uses ESPN venue metadata plus Open-Meteo. Weather is descriptive context; the
Tier 2 selection rule remains in matchup_advantages.select_waterfall.
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


def _weather_code_label(code):
    try:
        code = int(code)
    except (TypeError, ValueError, OverflowError):
        return "Conditions unavailable"
    if code == 0:
        return "Clear"
    if code == 1:
        return "Mainly clear"
    if code == 2:
        return "Partly cloudy"
    if code == 3:
        return "Overcast"
    if code in {45, 48}:
        return "Fog"
    if code in {51, 53, 55}:
        return "Drizzle"
    if code in {56, 57}:
        return "Freezing drizzle"
    if code in {61, 63, 65}:
        return "Rain"
    if code in {66, 67}:
        return "Freezing rain"
    if code in {71, 73, 75, 77}:
        return "Snow"
    if code in {80, 81, 82}:
        return "Rain showers"
    if code in {85, 86}:
        return "Snow showers"
    if code in THUNDER_CODES:
        return "Thunderstorms"
    return "Variable conditions"


def _series(hourly, key, length):
    raw = hourly.get(key)
    if not isinstance(raw, list) or len(raw) != length:
        raw = [None] * length
    return pd.to_numeric(pd.Series(raw), errors="coerce")


def _summarize_window(frame, kickoff, source_type):
    kickoff = pd.to_datetime(kickoff, utc=True, errors="coerce")
    if pd.isna(kickoff) or frame.empty:
        return None
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

    first = window.iloc[0]
    temp = float(first.temperature_2m) if pd.notna(first.temperature_2m) else math.nan
    feels = float(first.apparent_temperature) if pd.notna(first.apparent_temperature) else math.nan
    kickoff_code = int(first.weather_code) if pd.notna(first.weather_code) else None
    kickoff_wind = float(first.wind_speed_10m) if pd.notna(first.wind_speed_10m) else math.nan
    return {
        "status": "ok",
        "inclement": bool(wet or windy),
        "weather_type": weather_type,
        "condition": _weather_code_label(kickoff_code),
        "temperature_f": temp,
        "feels_like_f": feels,
        "kickoff_wind_mph": kickoff_wind,
        "precip_mm": precip,
        "snowfall": snow,
        "max_wind_mph": wind,
        "max_gust_mph": gust,
        "weather_codes": sorted(codes),
        "source_type": source_type,
    }


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
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "hourly": "temperature_2m,apparent_temperature,precipitation,snowfall,weather_code,wind_speed_10m,wind_gusts_10m",
    }
    if start_date < today:
        base = "https://historical-forecast-api.open-meteo.com/v1/forecast"
        source_type = "Historical game weather"
    else:
        base = "https://api.open-meteo.com/v1/forecast"
        source_type = "Forecast"
    payload = _json(base, params)
    hourly = payload.get("hourly") or {}
    times = pd.to_datetime(hourly.get("time", []), utc=True, errors="coerce")
    n = len(times)
    frame = pd.DataFrame({
        "time": times,
        "temperature_2m": _series(hourly, "temperature_2m", n),
        "apparent_temperature": _series(hourly, "apparent_temperature", n),
        "precipitation": _series(hourly, "precipitation", n),
        "snowfall": _series(hourly, "snowfall", n),
        "weather_code": _series(hourly, "weather_code", n),
        "wind_speed_10m": _series(hourly, "wind_speed_10m", n),
        "wind_gusts_10m": _series(hourly, "wind_gusts_10m", n),
    }).dropna(subset=["time"])
    return _summarize_window(frame, kickoff, source_type)


def build_weather_context(schedule, week, game_ids=None):
    """Return game-id keyed weather context for selected games.

    Outdoor games receive game-window weather when venue/location/kickoff data
    can be resolved. Indoor venues are identified explicitly. Neutral-site
    games can still receive weather for display; Tier 2 rejects neutral sites
    separately. game_ids can restrict network work to selected matchups.
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
        neutral = _truthy(game.get("neutral_site", False))
        try:
            venue_id = int(float(game.get("venue_id")))
        except (TypeError, ValueError, OverflowError):
            return gid, {"status": "missing", "inclement": False, "neutral_site": neutral,
                         "reason": "Venue ID unavailable."}
        try:
            venue = _venue(venue_id)
        except Exception:
            return gid, {"status": "missing", "inclement": False, "neutral_site": neutral,
                         "reason": "Venue metadata unavailable."}
        venue_name = str(venue.get("fullName") or game.get("venue") or "").strip()
        address = venue.get("address") or {}
        location = ", ".join(x for x in (str(address.get("city") or "").strip(),
                                          str(address.get("state") or "").strip()) if x)
        if venue.get("indoor") is True:
            return gid, {"status": "indoor", "inclement": False, "neutral_site": neutral,
                         "venue_name": venue_name, "location": location,
                         "reason": "Indoor venue."}
        if venue.get("indoor") is not False:
            return gid, {"status": "missing", "inclement": False, "neutral_site": neutral,
                         "venue_name": venue_name, "location": location,
                         "reason": "Venue roof status unavailable."}
        try:
            coords = _geocode(address)
        except Exception:
            coords = None
        if not coords:
            return gid, {"status": "missing", "inclement": False, "neutral_site": neutral,
                         "venue_name": venue_name, "location": location,
                         "reason": "Venue location unavailable."}
        kickoff = pd.to_datetime(game.get("start_date"), utc=True, errors="coerce")
        if pd.isna(kickoff):
            return gid, {"status": "missing", "inclement": False, "neutral_site": neutral,
                         "venue_name": venue_name, "location": location,
                         "reason": "Kickoff time unavailable."}
        try:
            weather = _hourly_weather(coords[0], coords[1], kickoff)
        except Exception:
            weather = None
        if not weather:
            return gid, {"status": "missing", "inclement": False, "neutral_site": neutral,
                         "venue_name": venue_name, "location": location,
                         "reason": "Weather unavailable."}
        weather.update(neutral_site=neutral, venue_name=venue_name, location=location)
        return gid, weather

    out = {}
    records = [row for _, row in games.iterrows()]
    with ThreadPoolExecutor(max_workers=min(12, max(1, len(records)))) as pool:
        for gid, weather in pool.map(one, records):
            if gid is not None:
                out[gid] = weather
    return out
