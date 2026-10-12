"""Schedule-driven capture of four unchanged research weight hypotheses.

GitHub Actions runs this independent collector, never app.py. All four models
freeze together on the first eligible verified pregame observation; settlement
is separate. No replayed/historical picks masquerade as prospective captures.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen
import json
import os

import pandas as pd

from shadow_inputs import read_summary, download_schedule, augment_missing_summaries
from matchup_advantages import normalize_fbs_schedule
from prospective_weights import pregame_predictions, configuration
from prospective_weights_archive import DATA, make_snapshot, settle, load
from value_archive import pregame_window


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def digest(frame):
    return sha256(frame.to_csv(index=False).encode("utf-8")).hexdigest()


def fetch(gid):
    url = ("https://site.api.espn.com/apis/site/v2/sports/football/"
           "college-football/summary?event=" + gid)
    with urlopen(url, timeout=25) as response:
        return json.load(response)


def main():
    log = load()
    schedule = download_schedule(2026)
    schedule = schedule.loc[
        schedule["season_type"].astype(str).str.lower().eq("regular")
    ].copy()
    schedule = normalize_fbs_schedule(schedule)
    schedule = schedule.copy()
    for col in ("season", "week", "game_id", "home_id", "away_id"):
        schedule[col] = pd.to_numeric(schedule[col], errors="coerce")
    schedule = schedule.dropna(subset=["season", "week", "game_id", "home_id", "away_id"])
    schedule = schedule.sort_values("start_date", kind="stable")

    now = pd.Timestamp.now(tz="UTC")
    kickoff = pd.to_datetime(schedule["start_date"], utc=True, errors="coerce")
    upcoming = schedule[
        kickoff.gt(now) & kickoff.le(now + pd.Timedelta(hours=18))
    ].copy()
    games = {
        str(int(game["game_id"])): game for _, game in upcoming.iterrows()
        if str(int(game["game_id"])) not in log["snapshots"]
    }
    unsettled = set(log["snapshots"]) - set(log["results"])
    ids = sorted(set(games) | unsettled)
    payloads, errors = {}, {}

    def request(gid):
        try:
            return gid, fetch(gid), None
        except Exception as exc:
            return gid, None, type(exc).__name__

    with ThreadPoolExecutor(max_workers=6) as pool:
        for gid, payload, error in pool.map(request, ids):
            if error:
                errors[gid] = error
            else:
                payloads[gid] = payload

    pending = {
        gid: game for gid, game in games.items()
        if gid in payloads and pregame_window(
            payloads[gid], game, utc_now(), hours=18
        )
    }
    captured, skipped, settled = 0, {}, 0
    if pending:
        current = read_summary(None, 2026)
        prior = read_summary(None, 2025)
        provenance = {
            "model_version": "V1.5",
            "model_sha256": sha256(Path("model_v1_5.py").read_bytes()).hexdigest(),
            "challenger_sha256": sha256(Path("prospective_weights.py").read_bytes()).hexdigest(),
            "schedule_sha256": digest(schedule),
            "current_summary_sha256": digest(current),
            "prior_summary_sha256": digest(prior),
            "git_sha": os.environ.get("GITHUB_SHA", "local"),
            "notes": "Four identical input snapshots; only offensive/defensive internal weights differ.",
        }
        for week in sorted({int(g["week"]) for g in pending.values()}):
            try:
                augmented, derived = augment_missing_summaries(
                    current, prior, schedule, week
                )
                probabilities = pregame_predictions(
                    augmented, prior, schedule, week
                )
                for gid, game in pending.items():
                    if int(game["week"]) != week:
                        continue
                    if gid not in probabilities:
                        skipped[gid] = "No production baseline prediction"
                        continue
                    origin = dict(provenance,
                                  week=week, stats_cutoff_exclusive_week=week,
                                  provisional_team_ids=sorted(int(t) for t in derived))
                    try:
                        snapshot = make_snapshot(
                            game, probabilities[gid], payloads[gid],
                            utc_now(), origin
                        )
                        if gid not in log["snapshots"]:
                            log["snapshots"][gid] = snapshot
                            captured += 1
                    except (ValueError, TypeError, KeyError, OverflowError) as exc:
                        skipped[gid] = str(exc)
            except Exception as exc:
                skipped[f"week_{week}"] = type(exc).__name__ + ": " + str(exc)

    # Never settle an event whose snapshot was first saved in this same run.
    for gid in unsettled:
        if gid not in payloads or gid in log["results"]:
            continue
        result = settle(log["snapshots"][gid], payloads[gid], utc_now())
        if result:
            log["results"][gid] = result
            settled += 1

    log["last_run"] = utc_now()
    log["run_summary"] = {
        "eligible_pregame_games": len(games),
        "fetched": len(payloads),
        "snapshots_added": captured,
        "results_added": settled,
        "total_locked": len(log["snapshots"]),
        "total_settled": len(log["results"]),
        "missing_event_feeds": errors,
        "skipped": skipped,
    }
    DATA.parent.mkdir(parents=True, exist_ok=True)
    temp = DATA.with_suffix(".tmp")
    temp.write_text(json.dumps(log, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temp.replace(DATA)
    print(json.dumps(log["run_summary"], indent=2))


if __name__ == "__main__":
    main()
