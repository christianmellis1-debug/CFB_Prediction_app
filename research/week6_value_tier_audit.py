"""Retrospective 2026 Week 6 tier audit.

Frozen pregame moneylines are taken from the separate forward-test archive.
The five-tier waterfall was NOT archived before the games; spread quotes and
weather obtained after the fact are retrospective and never labeled verified.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import pandas as pd

from shadow_inputs import download_schedule, read_summary, augment_missing_summaries
from model_v1_5 import predict_week, add_waterfall_value
from matchup_advantages import normalize_fbs_schedule, build_waterfall_profiles, weather_tier_candidate_ids
from weather_context import build_weather_context
from capture_value import boxes, fetch_event
from value_archive import event_quotes, market_fields, usable_quote, grade, roi


ROOT = Path("research/2026_week6_value_tier_audit.json")


def summarize(records):
    output = {}
    for stage in range(1, 6):
        rows = [x for x in records if x["stage"] == stage]
        graded = [x for x in rows if x["result"] in ("Win", "Loss", "Push")]
        priced = [x for x in graded if x["net_10"] is not None]
        profit = round(sum(x["net_10"] for x in priced), 2)
        output[str(stage)] = {
            "label": next((x["tier"] for x in rows), "Tier " + str(stage)),
            "selections_reconstructed": len(rows),
            "graded": len(graded),
            "wins": sum(x["result"] == "Win" for x in graded),
            "losses": sum(x["result"] == "Loss" for x in graded),
            "pushes": sum(x["result"] == "Push" for x in graded),
            "priced": len(priced),
            "profit_at_10": profit if priced else None,
            "roi_at_10": round(profit / (10 * len(priced)), 4) if priced else None,
        }
    return output


def main():
    archive = json.loads(Path("data/shadow_tracking.json").read_text())
    candidates = {gid: snap for gid, snap in archive["snapshots"].items()
                  if snap["season"] == 2026 and snap["week"] == 6
                  and gid in archive["results"]}
    schedule = download_schedule(2026)
    schedule = normalize_fbs_schedule(schedule)
    schedule = schedule[schedule["season_type"].astype(str).str.lower().eq("regular")].copy()
    for col in ("week", "game_id", "home_id", "away_id"):
        schedule[col] = pd.to_numeric(schedule[col], errors="coerce")
    game_frame = schedule[schedule.week.eq(6) & schedule.game_id.isin([int(x) for x in candidates])].copy()
    current = read_summary(None, 2026)
    prior = read_summary(None, 2025)
    adjusted, derived = augment_missing_summaries(current, prior, schedule, 6)
    pred = predict_week(adjusted, prior, schedule, 6, include_completed=True)
    pred = pred[pred["Game ID"].astype(int).isin([int(x) for x in candidates])].copy()
    box = boxes(2026)
    # Postgame event records are ONLY used to reconstruct missing spreads and
    # ATS quote prices; no retrospective quote becomes a verified archived line.
    def get(gid):
        try:
            return gid, fetch_event(gid)
        except Exception:
            return gid, {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        historical = dict(pool.map(get, candidates))
    game_by_id = {str(int(g.game_id)): g for _, g in game_frame.iterrows()}
    quotes_available = []
    for key in ("DK Home ML", "DK Away ML", "Home Spread", "Away Spread",
                "Home Spread Odds", "Away Spread Odds", "Spread Source"):
        pred[key] = "Unavailable"
    for idx, row in pred.iterrows():
        gid = str(int(row["Game ID"]))
        snap = candidates[gid]
        game = game_by_id.get(gid)
        if game is None:
            continue
        prices = market_fields(event_quotes(historical.get(gid, {})), game)
        # Tier 3 and Tier 4 MUST use the frozen quote rather than a postgame price.
        if snap["provider"].strip().lower().replace(" ", "") == "draftkings":
            prices["DK Home ML"] = f'{int(snap["home_ml"]):+d}'
            prices["DK Away ML"] = f'{int(snap["away_ml"]):+d}'
        for key, value in prices.items():
            pred.loc[idx, key] = value
        if prices["Home Spread"] != "Unavailable":
            quotes_available.append(gid)
    profiles = build_waterfall_profiles(schedule, box, 6)
    ids = weather_tier_candidate_ids(pred, schedule, profiles)
    weather = build_weather_context(schedule, 6, ids) if ids else {}
    scored = add_waterfall_value(pred, schedule, box, 6, weather_checks=weather, published_summary=current)
    results = []
    for _, pick in scored[scored["Value Selected"]].iterrows():
        gid = str(int(pick["Game ID"]))
        if gid not in game_by_id:
            continue
        g = game_by_id[gid]
        snap = candidates[gid]
        final = archive["results"][gid]
        record = {"selected": True, "Value Side": pick["Value Side"],
                  "Value Market": pick["Value Market"],
                  "Value Line": pick["Value Line"],
                  "Value Price": pick["Value Price"]}
        result = grade(record, final["home_score"], final["away_score"])
        price_origin = ("frozen DraftKings pregame moneyline" if pick["Value Market"] == "Moneyline"
                        and snap["provider"].lower().replace(" ", "") == "draftkings"
                        else "postgame ESPN reference (NOT locked pregame spread)")
        results.append({
            "event_id": gid, "matchup": f'{g.away_team} at {g.home_team}',
            "stage": int(pick["Value Stage"]), "tier": str(pick["Value Tier"]),
            "pick": str(pick["Value Pick"]),
            "market": str(pick["Value Market"]), "line": str(pick["Value Line"]),
            "price": str(pick["Value Price"]), "price_provenance": price_origin,
            "result": result, "away_score": final["away_score"], "home_score": final["home_score"],
            "net_10": roi(record, result, 10),
            "weather_status_retrospective": weather.get(gid, {}).get("status", "not-requested"),
        })
    # A separate price-bucket audit is truly verifiable from locked pregame
    # moneylines but is NOT equivalent to the final priority-ranked Tier 4 card.
    price_bucket = []
    for gid, s in sorted(candidates.items()):
        if s["provider"].lower().replace(" ", "") != "draftkings":
            continue
        home, away = usable_quote(s["home_ml"]), usable_quote(s["away_ml"])
        if home is None or away is None:
            continue
        fav = min(home, away)
        if not (-1000 <= fav <= -505):
            continue
        winner = "home" if home < away else "away"
        final = archive["results"][gid]
        actual = "home" if final["home_score"] > final["away_score"] else "away"
        win = winner == actual
        net = round(10 * 100 / abs(fav), 2) if win else -10.0
        price_bucket.append({"event_id": gid, "matchup": f'{s["away"]} at {s["home"]}',
                             "favorite": s["home"] if winner == "home" else s["away"],
                             "moneyline": fav, "result": "Win" if win else "Loss",
                             "net_10": net, "locked_at": s["captured_at"]})
    price_net = round(sum(x["net_10"] for x in price_bucket), 2)
    output = {
        "season": 2026, "week": 6,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "RETROSPECTIVE RECONSTRUCTION; NOT THE ORIGINAL WEEK 6 PUBLISHED FIVE-TIER CARD",
        "coverage": {"frozen_pregame_moneyline_games": len(candidates),
                     "games_matched_to_schedule": len(game_frame),
                     "postgame_spread_reference_games": len(quotes_available),
                     "derived_fallback_team_ids": sorted(int(x) for x in derived),
                     "weather_candidate_count": len(ids)},
        "tier_summary": summarize(results), "reconstructed_picks": results,
        "tier4_independent_frozen_price_band": {
            "note": "These are independently priced candidates, not necessarily official Tier 4 selections; earlier tiers take priority.",
            "selections": len(price_bucket),
            "wins": sum(x["result"] == "Win" for x in price_bucket),
            "losses": sum(x["result"] == "Loss" for x in price_bucket),
            "net_at_10": price_net,
            "roi": round(price_net / (len(price_bucket) * 10), 4) if price_bucket else None,
            "games": price_bucket,
        },
        "limitations": [
            "Original Tier 1/2 spread lines and tier-selection decisions were not frozen prior to Week 6.",
            "Reconstructed ATS lines may differ from those available at kickoff.",
            "Historical weather or revised team summaries may differ from the original pregame inputs.",
            "Missing market/box/forecast coverage can suppress retrospective qualifiers.",
            "All five-tier results are exploratory; never relabel historical reconstructions as forward tested."
        ],
    }
    ROOT.parent.mkdir(exist_ok=True)
    ROOT.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"coverage": output["coverage"],
                      "tier_summary": output["tier_summary"],
                      "frozen_price_bucket": output["tier4_independent_frozen_price_band"]},
                     indent=2))


if __name__ == "__main__":
    main()
