"""Historical Tier 1 vs Prime-only ATS audit (research branch, no production edits).

Rerun with: python tests/test_prime_only_historical.py
Source feeds: sportsdataverse public schedules, ESPN team boxes and ESPN-derived lines.
Results are retrospective and closing/archived line estimates, not locked bets.
"""
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from urllib.request import Request, urlopen

import pandas as pd

from matchup_advantages import assess, build_advantages

YEAR_SET = (2024, 2025)
URLS = {
    "schedule": "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{year}.csv",
    "box": "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_{year}.csv",
    "betting": "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_betting/betting_{year}.csv",
}
BANDS = {
    "prime": lambda s: -13.5 <= s <= -7,
    "standard": lambda s: -7 < s <= 0,
    "heavy": lambda s: s < -13.5,
    "underdog": lambda s: s > 0,
}


def load(item):
    key, url = item
    req = Request(url, headers={"User-Agent": "SaturdayForecast-PrimeResearch/1.0"})
    with urlopen(req, timeout=100) as response:
        data = response.read()
    print("FEED", key, "bytes", len(data), flush=True)
    return key, pd.read_csv(BytesIO(data), low_memory=False)


def true_series(column):
    return column.astype(str).str.lower().str.strip().isin(
        ("true", "t", "1", "1.0", "yes", "y"))


def count(rows):
    valid = [r for r in rows if r["outcome"] in ("Win", "Loss", "Push")]
    w = sum(r["outcome"] == "Win" for r in valid)
    l = sum(r["outcome"] == "Loss" for r in valid)
    p = sum(r["outcome"] == "Push" for r in valid)
    return {
        "picks": len(rows), "wins": w, "losses": l, "pushes": p,
        "win_pct_ex_pushes": round(100 * w / (w + l), 2) if w + l else None,
        "avg_cover_margin": round(sum(r["cover_margin"] for r in valid) / len(valid), 2) if valid else None,
    }


def yearly_audit(year):
    feeds = dict(ThreadPoolExecutor(max_workers=3).map(
        load, ((key, pattern.format(year=year)) for key, pattern in URLS.items())))
    schedule, boxes, betting = feeds["schedule"], feeds["box"], feeds["betting"]
    print("COLUMNS", year, "betting", list(betting.columns), flush=True)
    print("COLUMNS", year, "box", list(boxes.columns), flush=True)
    required = {"game_id", "home_team_spread", "game_spread_available"}
    if not required.issubset(betting.columns):
        raise ValueError(f"{year} missing betting columns: {required - set(betting.columns)}")
    lines = betting.copy()
    lines["game_id"] = pd.to_numeric(lines["game_id"], errors="coerce")
    lines["home_team_spread"] = pd.to_numeric(lines["home_team_spread"], errors="coerce")
    lines = lines[
        true_series(lines["game_spread_available"])
        & lines["game_id"].notna()
        & lines["home_team_spread"].notna()
    ].copy()
    if "odds_source" in lines.columns:
        lines = lines[~lines["odds_source"].astype(str).str.lower().eq("default")]
    conflicting = set(lines.loc[lines.duplicated("game_id", keep=False), "game_id"].astype(int))
    lines = lines[~lines["game_id"].isin(conflicting)]
    quote_lookup = dict(zip(lines["game_id"].astype(int), lines["home_team_spread"]))

    s = schedule[
        schedule["season_type"].astype(str).str.lower().eq("regular")
        & schedule["home_division"].astype(str).str.lower().eq("fbs")
        & schedule["away_division"].astype(str).str.lower().eq("fbs")
    ].copy()
    for column in ("game_id", "week", "home_points", "away_points", "home_id", "away_id"):
        s[column] = pd.to_numeric(s[column], errors="coerce")
    s = s.dropna(subset=["game_id", "week", "home_id", "away_id"])
    s["start_date"] = pd.to_datetime(s["start_date"], errors="coerce", utc=True)
    s = s.dropna(subset=["start_date"])
    if s.game_id.duplicated().any():
        raise ValueError(f"{year} ambiguous FBS game IDs")
    games_with_final = s[
        true_series(s["completed"]) & s.home_points.notna() & s.away_points.notna()
    ]
    raw_qualifiers = []
    covered = []
    candidate_counts = {}
    for week in sorted(s["week"].unique()):
        if week < 2:
            continue
        check = build_advantages(s, boxes, int(week))
        games = games_with_final[games_with_final["week"].eq(week)]
        qualifying = 0
        for _, game in games.iterrows():
            gid = str(int(game.game_id))
            record = check.get(gid, {})
            if record.get("status") != "ok" or true_series(pd.Series([game["neutral_site"]])).iloc[0]:
                continue
            result = assess(record, "home")
            if result is None or result["count"] != 5:
                continue
            qualifying += 1
            raw_qualifiers.append(gid)
            spread = quote_lookup.get(int(gid))
            if spread is None:
                continue
            margin = float(game.home_points - game.away_points) + float(spread)
            band = next((k for k, pred in BANDS.items() if pred(spread)), "unclassified")
            covered.append({
                "season": int(year), "week": int(week),
                "event_id": gid, "home": str(game.home_team), "away": str(game.away_team),
                "home_spread": float(spread), "band": band,
                "home_points": int(game.home_points), "away_points": int(game.away_points),
                "cover_margin": round(margin, 2),
                "outcome": "Win" if margin > 1e-7 else "Loss" if margin < -1e-7 else "Push",
            })
        candidate_counts[str(int(week))] = qualifying

    if len(games_with_final) < 100:
        raise AssertionError(f"Unexpectedly few completed FBS games for {year}")
    return {
        "year": year,
        "fbs_completed_games": len(games_with_final),
        "book_graded_games": len(quote_lookup),
        "six_of_six_raw_qualifiers": len(raw_qualifiers),
        "six_of_six_with_valid_spread": len(covered),
        "six_of_six_missing_spread": len(raw_qualifiers) - len(covered),
        "by_week_candidates": candidate_counts,
        "tier_1_all": count(covered),
        "prime_only": count([r for r in covered if r["band"] == "prime"]),
        "bands": {band: count([r for r in covered if r["band"] == band]) for band in BANDS},
        "prime_games": [r for r in covered if r["band"] == "prime"],
    }


class TestPrimeOnlyHistorical(unittest.TestCase):
    def test_historical_2024_2025(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = sorted(pool.map(yearly_audit, YEAR_SET), key=lambda x: x["year"])
        total = {
            "baseline": count([
                {"outcome": "Win", "cover_margin": 0} for a in results for _ in range(a["tier_1_all"]["wins"])
            ] + [
                {"outcome": "Loss", "cover_margin": 0} for a in results for _ in range(a["tier_1_all"]["losses"])
            ] + [
                {"outcome": "Push", "cover_margin": 0} for a in results for _ in range(a["tier_1_all"]["pushes"])
            ]),
            "prime": count([
                {"outcome": "Win", "cover_margin": 0} for a in results for _ in range(a["prime_only"]["wins"])
            ] + [
                {"outcome": "Loss", "cover_margin": 0} for a in results for _ in range(a["prime_only"]["losses"])
            ] + [
                {"outcome": "Push", "cover_margin": 0} for a in results for _ in range(a["prime_only"]["pushes"])
            ]),
        }
        print("PRIME_ONLY_HISTORICAL_REPORT=" + json.dumps({
            "note": "RETROSPECTIVE reconstruction; ESPN-derived archived spreads are not locked pregame odds",
            "yearly": results, "combined": total,
        }, allow_nan=False), flush=True)
        self.assertGreater(sum(r["six_of_six_with_valid_spread"] for r in results), 0)
        self.assertGreater(sum(r["prime_only"]["picks"] for r in results), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
