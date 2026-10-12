"""Scheduled prospective capture of Saturday Forecast's official tier decisions.

Run by GitHub Actions; does not import or execute Streamlit app.py.
Snapshots are immutable; only separate final results and run status are updated.
"""
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

import pandas as pd

from shadow_inputs import download_schedule, read_summary, augment_missing_summaries
from model_v1_5 import predict_week, add_waterfall_value
from matchup_advantages import normalize_fbs_schedule, build_waterfall_profiles, weather_tier_candidate_ids
from weather_context import build_weather_context
from value_archive import event_quotes, market_fields, make_archive, pregame_window, settle

OUT = Path("data/value_archive_2026.json")


def now():
    return datetime.now(timezone.utc).isoformat()


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fetch_event(event_id):
    url = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event=" + str(event_id)
    with urlopen(url, timeout=25) as stream:
        return json.load(stream)


def boxes(year):
    url = f"https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_{year}.csv"
    with urlopen(url, timeout=75) as stream:
        return pd.read_csv(stream, low_memory=False)


def archive_row(game, pick, payload, captured_at, source):
    doc = make_archive(game, pick, payload, captured_at, source)
    doc["market"] = market_fields(event_quotes(payload), game)
    doc["quote_status"] = ("DraftKings" if doc["market"]["DK Home ML"] != "Unavailable"
                           and doc["market"]["DK Away ML"] != "Unavailable"
                           else "Incomplete/missing DraftKings two-sided moneyline")
    return doc


def main():
    if OUT.exists():
        log = json.loads(OUT.read_text())
    else:
        log = {"schema": 1, "season": 2026, "snapshots": {}, "results": {}, "run_status": {}}
    if log.get("schema") != 1 or log.get("season") != 2026:
        raise ValueError("Archive schema/season mismatch: refusing to overwrite")
    log.setdefault("snapshots", {})
    log.setdefault("results", {})
    schedule = download_schedule(2026)
    schedule = schedule[schedule["season_type"].astype(str).str.lower().eq("regular")].copy()
    schedule = normalize_fbs_schedule(schedule)
    for col in ("season", "week", "game_id", "home_id", "away_id"):
        schedule[col] = pd.to_numeric(schedule[col], errors="coerce")
    schedule = schedule.dropna(subset=["week", "game_id", "home_id", "away_id"])
    schedule = schedule.sort_values("start_date", kind="stable")
    eligible = schedule[pd.to_datetime(schedule["start_date"], utc=True, errors="coerce")
                        .between(pd.Timestamp.now(tz="UTC"),
                                 pd.Timestamp.now(tz="UTC") + pd.Timedelta(hours=18))].copy()
    # Refresh unsettled games separately so that all results use the saved side and line.
    unfinished = set(log["snapshots"]) - set(log["results"])
    games = {str(int(row["game_id"])): row for _, row in eligible.iterrows()}
    ids = sorted(set(games) | unfinished)
    fetched = {}
    errors = []
    def get(event_id):
        try:
            return event_id, fetch_event(event_id), None
        except Exception as exc:
            return event_id, None, type(exc).__name__
    with ThreadPoolExecutor(max_workers=6) as pool:
        for event_id, payload, error in pool.map(get, ids):
            if error:
                errors.append({"event": event_id, "error": error})
            else:
                fetched[event_id] = payload

    captured = 0
    skipped = {}
    pending = {gid: row for gid, row in games.items()
               if gid not in log["snapshots"] and gid in fetched
               and pregame_window(fetched[gid], row, now(), hours=18)}
    if pending:
        current = read_summary(None, 2026)
        prior = read_summary(None, 2025)
        box = boxes(2026)
        box_hash = hashlib.sha256(pd.util.hash_pandas_object(box, index=True).values.tobytes()).hexdigest()
        summary_hash = hashlib.sha256(pd.util.hash_pandas_object(current, index=True).values.tobytes()).hexdigest()
        for week in sorted(set(int(row["week"]) for row in pending.values())):
            try:
                augmented, fallback = augment_missing_summaries(current, prior, schedule, week)
                predictions = predict_week(augmented, prior, schedule, week, include_completed=True)
                if predictions.empty:
                    raise ValueError("Empty predictions")
                predictors = predictions.set_index(pd.to_numeric(predictions["Game ID"], errors="coerce"))
                for event_id, row in pending.items():
                    if int(row["week"]) != week:
                        continue
                    if int(event_id) in predictors.index:
                        quote = market_fields(event_quotes(fetched[event_id]), row)
                        for key, value in quote.items():
                            predictors.loc[int(event_id), key] = value
                predictions = predictors.reset_index(drop=True)
                profiles = build_waterfall_profiles(schedule, box, week)
                candidates = weather_tier_candidate_ids(predictions, schedule, profiles)
                weather = build_weather_context(schedule, week, candidates) if candidates else {}
                scored = add_waterfall_value(predictions, schedule, box, week,
                                             weather_checks=weather, published_summary=current,
                                             prior_summary=prior)
                lookup = {str(int(x["Game ID"])): x for _, x in scored.iterrows()}
                for gid, game in pending.items():
                    if int(game["week"]) != week or gid not in lookup:
                        continue
                    source = {
                        "model": "production model_v1_5.predict_week",
                        "waterfall": "production model_v1_5.add_waterfall_value",
                        "commit": os.environ.get("GITHUB_SHA", "local"),
                        "summary_sha256": summary_hash,
                        "box_sha256": box_hash,
                        "stats_cutoff_exclusive_week": week,
                        "fallback_team_ids": sorted(int(tid) for tid in fallback),
                        "weather_status": weather.get(gid, {}).get("status", "not-requested"),
                    }
                    captured_at = now()
                    try:
                        doc = archive_row(game, lookup[gid], fetched[gid], captured_at, source)
                        # Store actual market fields from the same response used by selection.
                        log["snapshots"].setdefault(gid, doc)
                        captured += 1
                    except (ValueError, KeyError, TypeError) as exc:
                        skipped[gid] = str(exc)
            except Exception as exc:
                skipped["week_" + str(week)] = type(exc).__name__ + ": " + str(exc)
    settled = 0
    for gid in unfinished:
        if gid in fetched and gid not in log["results"]:
            result = settle(log["snapshots"][gid], fetched[gid], now())
            if result:
                log["results"][gid] = result
                settled += 1
    # Do not settle a capture from the same run; only a later verified final.
    log["run_status"] = {"checked_at": now(), "new_snapshots": captured,
                         "new_results": settled, "eligible_in_window": len(games),
                         "missing_events": errors, "skipped": skipped,
                         "selected_total": sum(bool(x["selected"]) for x in log["snapshots"].values())}
    OUT.parent.mkdir(exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(log, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.replace(OUT)
    print(json.dumps(log["run_status"], indent=2))


if __name__ == "__main__":
    main()
