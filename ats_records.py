"""Season-to-date, pregame ATS records from verified ESPN-derived closing spreads.

Only completed FBS-versus-FBS regular-season games before the selected week
count. A missing spread is never silently treated as a pick'em line.
"""
from io import BytesIO
from urllib.request import urlopen

import pandas as pd


BETTING_URL = (
    "https://github.com/sportsdataverse/sportsdataverse-data/releases/"
    "download/espn_cfb_betting/betting_{year}.csv"
)


def download_ats_lines(year):
    """Fetch compact, public ESPN-derived game spreads (one download per cache TTL)."""
    with urlopen(BETTING_URL.format(year=int(year)), timeout=20) as response:
        return pd.read_csv(BytesIO(response.read()), low_memory=False)


def _is_true(values):
    return values.astype(str).str.strip().str.lower().isin(("true", "t", "1", "1.0", "yes", "y"))


def _ids(frame, column):
    return pd.to_numeric(frame[column], errors="coerce")


def calculate_ats_records(schedule, lines, week):
    """Return per-team W-L-P and graded/eligible coverage through prior weeks.

    Schedule is already constrained to regular-season FBS matchups by the app.
    Enforce those constraints again when columns are provided to keep this
    routine safe to use independently in tests and other views.
    The betting table uses home-relative lines (negative = home favorite).
    """
    if schedule is None or schedule.empty:
        return {}
    games = schedule.copy()
    needed = ("week", "home_id", "away_id", "home_points", "away_points", "game_id")
    if any(col not in games for col in needed):
        return {}
    games["week"] = _ids(games, "week")
    games = games[(games["week"] < int(week)) & (games["week"] >= 1)].copy()
    if "season_type" in games:
        games = games[games["season_type"].astype(str).str.lower().eq("regular")]
    if "fbs_game" in games:
        games = games[_is_true(games["fbs_game"])]
    if "completed" in games:
        games = games[_is_true(games["completed"])]
    for field in ("game_id", "home_id", "away_id", "home_points", "away_points"):
        games[field] = _ids(games, field)
    games = games.dropna(subset=("game_id", "home_id", "away_id", "home_points", "away_points"))
    games = games.drop_duplicates(subset="game_id", keep="last")
    if games.empty:
        return {}

    valid_lines = {}
    if lines is not None and not lines.empty:
        if all(k in lines for k in ("game_id", "home_team_spread", "game_spread_available")):
            market = lines.copy()
            market["game_id"] = _ids(market, "game_id")
            market["home_team_spread"] = _ids(market, "home_team_spread")
            market = market[_is_true(market["game_spread_available"])]
            if "odds_source" in market:
                market = market[~market["odds_source"].astype(str).str.lower().eq("default")]
            market = market.dropna(subset=("game_id", "home_team_spread"))
            market = market.drop_duplicates(subset="game_id", keep="last")
            valid_lines = dict(zip(market["game_id"].astype(int), market["home_team_spread"]))

    records = {}
    for _, game in games.iterrows():
        home_id, away_id = int(game["home_id"]), int(game["away_id"])
        for team_id in (home_id, away_id):
            records.setdefault(team_id, {"wins": 0, "losses": 0, "pushes": 0, "graded": 0, "eligible": 0})
            records[team_id]["eligible"] += 1
        spread = valid_lines.get(int(game["game_id"]))
        if spread is None:
            continue
        margin = float(game["home_points"]) - float(game["away_points"]) + float(spread)
        home_result = "wins" if margin > 1e-7 else "losses" if margin < -1e-7 else "pushes"
        away_result = "losses" if home_result == "wins" else "wins" if home_result == "losses" else "pushes"
        for team_id, outcome in ((home_id, home_result), (away_id, away_result)):
            records[team_id][outcome] += 1
            records[team_id]["graded"] += 1
    return records


def calculate_overall_records(schedule, week, season=None):
    """Straight-up W-L through the prior week, including FCS opponents.

    Keep regular-season completed games with verified scores. Unlike ATS, an
    actual win/loss does not require a betting line or an FBS opponent.
    """
    if schedule is None or schedule.empty:
        return {}
    needed = {"week", "home_id", "away_id", "home_points", "away_points"}
    if not needed.issubset(schedule.columns):
        return {}
    games = schedule.copy()
    games["week"] = _ids(games, "week")
    games = games[games["week"].ge(0) & games["week"].lt(int(week))].copy()
    if season is not None:
        if "season" not in games:
            return {}
        games = games[pd.to_numeric(games["season"], errors="coerce").eq(int(season))]
    if "season_type" in games:
        games = games[games["season_type"].astype(str).str.lower().eq("regular")]
    if "completed" not in games:
        return {}
    games = games[_is_true(games["completed"])].copy()
    for field in ("home_id", "away_id", "home_points", "away_points"):
        games[field] = _ids(games, field)
    games = games.dropna(subset=("home_id", "away_id", "home_points", "away_points"))
    if "game_id" in games:
        games["game_id"] = _ids(games, "game_id")
        # Some uploaded files omit game IDs; do not discard their valid scores.
        games["_unique_game"] = games["game_id"].astype("string").fillna(
            games["week"].astype("string") + "/" +
            games["home_id"].astype("string") + "/" +
            games["away_id"].astype("string")
        )
        games = games.drop_duplicates(subset="_unique_game", keep="last")
    else:
        games = games.drop_duplicates(subset=("week", "home_id", "away_id"), keep="last")

    records = {}
    for _, game in games.iterrows():
        home_id, away_id = int(game["home_id"]), int(game["away_id"])
        if home_id == away_id:
            continue
        home_points, away_points = float(game["home_points"]), float(game["away_points"])
        if home_points == away_points:
            continue  # no football tie should be graded as a win or loss
        for tid, won in ((home_id, home_points > away_points),
                         (away_id, away_points > home_points)):
            record = records.setdefault(tid, {"wins": 0, "losses": 0})
            record["wins" if won else "losses"] += 1
    return records


def overall_ats_label(overall, ats, ats_feed_available=True):
    """Display actual W-L directly before the independent ATS record."""
    if overall is None:
        overall_label = "W–L 0–0"
    else:
        overall_label = f"W–L {int(overall['wins'])}–{int(overall['losses'])}"
    return overall_label + " · " + ats_label(ats, ats_feed_available)


def ats_label(record, feed_available=True):
    """Small, honest card label. Coverage warning when lines are missing."""
    if not feed_available:
        return "ATS unavailable"
    if record is None or not record["eligible"]:
        return "ATS 0–0–0"
    wins, losses, pushes = record["wins"], record["losses"], record["pushes"]
    graded, eligible = record["graded"], record["eligible"]
    value = f"ATS {wins}–{losses}–{pushes}"
    if graded < eligible:
        value += f" · {graded}/{eligible} lined"
    return value
