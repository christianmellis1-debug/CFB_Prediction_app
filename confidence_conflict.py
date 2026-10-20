"""Prospective G6 confidence-conflict risk screen (research warning, not a forecast).

Compare the independent, pre-market V1.5 side against two-sided moneylines
from ONE sportsbook. In-play/settled matches require a real frozen pregame
snapshot. Missing conferences, odds, timestamps or stale odds fail closed.
"""
import math
from datetime import datetime, timezone

import pandas as pd


P4 = {"ACC", "Big Ten", "Big 12", "SEC"}
G6 = {"American Athletic", "Conference USA", "Mid-American",
      "Mountain West", "Sun Belt"}
MODEL_MIN = .70
MARKET_MAX = .55


def conference_tier(conference, team, season):
    if str(team).strip().casefold() == "notre dame":
        return "P4"
    if conference in P4:
        return "P4"
    if conference in G6:
        return "G6"
    # The two-team Pac-12 is not counted as G6 in earlier research years.
    if str(conference) == "Pac-12" and season >= 2026:
        return "G6"
    return None


def implied(american):
    try:
        line = float(str(american).strip().replace("−", "-").replace("+", ""))
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(line) or abs(line) < 100 or not line.is_integer():
        return None
    return 100 / (100 + line) if line > 0 else -line / (100 - line)


def paired_market_probability(home_ml, away_ml, selected_side):
    """No-vig probability for the independent V1.5 side, not its blended pick."""
    h, a = implied(home_ml), implied(away_ml)
    if h is None or a is None or selected_side not in ("home", "away"):
        return None
    total = h + a
    if not 1 <= total <= 1.16:
        return None
    return (h if selected_side == "home" else a) / total


def timestamp(value):
    try:
        dt = pd.to_datetime(value, errors="coerce", utc=True)
        return dt if pd.notna(dt) else None
    except (ValueError, TypeError, OverflowError):
        return None


def apply_g6_conflict_flags(predictions, schedule, *,
                            now_utc=None, stale=False,
                            stale_event_ids=(), frozen_snapshots=None):
    """Return new flag columns; preserve model, tiers, prices and grades.

    Scheduled pregame: use current paired quotes only if the live odds feed is
    fresh. After kickoff: use the immutable first pregame shadow snapshot.
    """
    out = predictions.copy(deep=True)
    out["G6 Confidence Conflict"] = False
    out["Conflict V1.5 %"] = float("nan")
    out["Conflict Market %"] = float("nan")
    out["Conflict Team"] = ""
    out["Conflict Odds Source"] = ""
    # Separate observational flag: selected G6 home underdog at +150 or longer.
    # It never promotes a candidate into the official waterfall or a parlay.
    out["G6 Home Underdog Research"] = False
    out["G6 Home Underdog Secondary"] = False
    out["Research Underdog Band"] = ""
    out["Research Underdog Team"] = ""
    out["Research Underdog ML"] = float("nan")
    out["Research Underdog Model %"] = float("nan")
    out["Research Underdog Market %"] = float("nan")
    out["Research Underdog Book"] = ""
    if out.empty or "game_id" not in schedule:
        return out

    now = timestamp(now_utc if now_utc is not None else datetime.now(timezone.utc))
    if now is None:
        return out
    snapshots = frozen_snapshots or {}
    stale_ids = set(str(k) for k in (stale_event_ids or ()))
    games = {}
    duplicates = set()
    for _, game in schedule.iterrows():
        try:
            gid = str(int(game["game_id"]))
        except (TypeError, ValueError, OverflowError, KeyError):
            continue
        if gid in games:
            duplicates.add(gid)
        games[gid] = game

    for index, row in out.iterrows():
        try:
            gid = str(int(row["Game ID"]))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if gid not in games or gid in duplicates:
            continue
        game = games[gid]
        try:
            season = int(game["season"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if any(conference_tier(game.get(side + "_conference"),
                               game.get(side + "_team"), season) != "G6"
               for side in ("home", "away")):
            continue
        if (str(game.get("home_division")).lower() != "fbs" or
                str(game.get("away_division")).lower() != "fbs"):
            continue
        if (str(row.get("Home Team")) != str(game.get("home_team")) or
                str(row.get("Away Team")) != str(game.get("away_team"))):
            continue
        kickoff = timestamp(game.get("start_date"))
        if kickoff is None:
            continue
        side = str(row.get("Predicted Side", "")).lower()
        if side not in ("home", "away"):
            continue
        try:
            base_p = float(row.get("Confidence"))
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(base_p) or not 0.5 <= base_p <= 1:
            continue
        provider = None
        book_probability = None
        selected_moneyline = None
        if (now < kickoff and str(row.get("Status")) == "Awaiting final"):
            if stale or gid in stale_ids:
                continue
            provider = str(row.get("ML Source", "Unavailable"))
            if provider in ("", "Unavailable", "nan", "None"):
                continue
            book_probability = paired_market_probability(
                row.get("Home ML"), row.get("Away ML"), side)
            selected_moneyline = row.get("Home ML") if side == "home" else row.get("Away ML")
        else:
            frozen = snapshots.get(gid)
            if not isinstance(frozen, dict):
                continue
            captured = timestamp(frozen.get("captured_at"))
            frozen_kickoff = timestamp(frozen.get("kickoff"))
            if (captured is None or frozen_kickoff is None or
                    not captured < min(kickoff, frozen_kickoff)):
                continue
            if (str(frozen.get("home")) != str(game.get("home_team")) or
                    str(frozen.get("away")) != str(game.get("away_team")) or
                    str(frozen.get("home_id")) != str(int(game.get("home_id"))) or
                    str(frozen.get("away_id")) != str(int(game.get("away_id")))):
                continue
            if frozen.get("picked_side") not in ("home", "away"):
                continue
            side = frozen["picked_side"]
            try:
                base_p = float(frozen["model_probability"])
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            if not math.isfinite(base_p) or not 0.5 <= base_p <= 1:
                continue
            provider = str(frozen.get("provider") or "")
            if not provider:
                continue
            book_probability = paired_market_probability(
                frozen.get("home_ml"), frozen.get("away_ml"), side)
            selected_moneyline = frozen.get("home_ml") if side == "home" else frozen.get("away_ml")
        if book_probability is None:
            continue
        # Research only. Require independent V1.5 to pick the home team,
        # valid same-book two-sided prices, and an outright home dog +150+.
        # Keep the gate distinct from the 70/55 safety warning.
        try:
            home_line = float(str(selected_moneyline).strip().replace("+", "").replace("−", "-"))
        except (TypeError, ValueError, OverflowError):
            home_line = float("nan")
        if (side == "home" and 0.5 <= base_p <= 1.0
                and math.isfinite(home_line) and home_line.is_integer()
                and home_line >= 150 and book_probability < .5):
            # The +199 cutoff is a frozen research hypothesis, not a
            # validated profitability threshold. Keep +200+ games as
            # a separate secondary observational cohort to avoid losing
            # prospectively comparable outcomes.
            primary = home_line <= 199
            out.at[index, "G6 Home Underdog Research"] = primary
            out.at[index, "G6 Home Underdog Secondary"] = not primary
            out.at[index, "Research Underdog Band"] = (
                "Primary: +150 to +199" if primary else "Secondary: +200 or longer"
            )
            out.at[index, "Research Underdog Team"] = str(game["home_team"])
            out.at[index, "Research Underdog ML"] = home_line
            out.at[index, "Research Underdog Model %"] = base_p
            out.at[index, "Research Underdog Market %"] = book_probability
            out.at[index, "Research Underdog Book"] = provider
        if base_p >= MODEL_MIN and book_probability < MARKET_MAX:
            out.at[index, "G6 Confidence Conflict"] = True
            out.at[index, "Conflict V1.5 %"] = base_p
            out.at[index, "Conflict Market %"] = book_probability
            out.at[index, "Conflict Team"] = str(game[side + "_team"])
            out.at[index, "Conflict Odds Source"] = provider
    return out


def omit_risky_value_recommendations(predictions):
    """Keep risky games visible, but remove future official Value Picks.

    Existing historical grades and original candidate metadata are preserved.
    No change to the separate predicted winner or either ATS/ML model.
    """
    out = predictions.copy(deep=True)
    if "G6 Confidence Conflict" not in out or "Value Selected" not in out:
        return out
    mask = (
        out["G6 Confidence Conflict"].fillna(False).eq(True)
        & out["Value Selected"].fillna(False).eq(True)
        & out["Status"].eq("Awaiting final")
    )
    if not mask.any():
        return out
    out.loc[mask, "Value Selected"] = False
    out.loc[mask, "Bet Signal"] = "Pass · high-risk G6 conflict"
    out.loc[mask, "Value Rank"] = 0
    # Preserve original candidate metadata for investigation, but do not
    # advertise the game as a selected Value Pick or featured recommendation.
    if "Game of Week" in out:
        out.loc[mask, "Game of Week"] = False
    return out
