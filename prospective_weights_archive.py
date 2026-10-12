"""Immutable same-game pregame snapshots and independent final grades for 4 weights.

The snapshot is permanently preserved. Only the separate final result may
arrive later. Pending/invalid/missing results are never counted as losses.
"""
import math
from datetime import datetime, timezone
from pathlib import Path
import json

import pandas as pd

from prospective_weights import EXPERIMENT, CHALLENGERS, configuration
from value_archive import pregame_window, parse_time

DATA = Path(__file__).resolve().parent / "data" / "prospective_weights_2026.json"


def make_snapshot(game, predictions, payload, captured_at, provenance):
    gate = pregame_window(payload, game, captured_at, hours=18)
    if not gate:
        raise ValueError("Game is not verified pregame within 18 hours of kickoff")
    if set(predictions) != set(CHALLENGERS):
        raise ValueError("Missing one or more predefined challenger probabilities")
    cleaned = {}
    for name, value in predictions.items():
        p = float(value)
        if not (math.isfinite(p) and 0 < p < 1):
            raise ValueError(f"Invalid probability for {name}")
        cleaned[name] = {"home_win_probability": p,
                         "predicted_side": "home" if p >= 0.5 else "away",
                         "confidence": max(p, 1-p)}
    gid = str(int(game["game_id"]))
    return {
        "event_id": gid, "season": int(game["season"]), "week": int(game["week"]),
        "home_id": str(int(game["home_id"])), "away_id": str(int(game["away_id"])),
        "home": str(game["home_team"]), "away": str(game["away_team"]),
        "captured_at": parse_time(captured_at).isoformat(),
        **gate, "experiment": EXPERIMENT, "models": cleaned,
        "definitions": configuration(), "provenance": provenance
    }


def settle(snapshot, payload, checked_at):
    """Require verified final and same teams; don't grade a postponed game."""
    try:
        header = payload["header"]
        if str(header["id"]) != snapshot["event_id"]:
            return None
        competitions = header["competitions"]
        if len(competitions) != 1:
            return None
        c = competitions[0]
        typ = c["status"]["type"]
        if not typ.get("completed") or typ.get("name") not in (
            "STATUS_FINAL", "STATUS_FINAL_OVERTIME"
        ):
            return None
        competitors = {x["homeAway"]: x for x in c["competitors"]}
        for side in ("home", "away"):
            if str(competitors[side]["team"]["id"]) != snapshot[side + "_id"]:
                return None
        home = float(competitors["home"]["score"])
        away = float(competitors["away"]["score"])
        if not (math.isfinite(home) and math.isfinite(away) and home >= 0 and away >= 0):
            return None
        return {
            "home_score": home, "away_score": away,
            "winner_side": "home" if home > away else "away" if away > home else "tie",
            "checked_at": parse_time(checked_at).isoformat()
        }
    except (KeyError, ValueError, TypeError, OverflowError):
        return None


def empty_archive():
    return {"schema": 1, "experiment": EXPERIMENT, "season": 2026,
            "snapshots": {}, "results": {}, "last_run": None, "run_summary": {}}


def load():
    if DATA.exists():
        doc = json.loads(DATA.read_text())
    else:
        doc = empty_archive()
    if doc.get("schema") != 1 or doc.get("experiment") != EXPERIMENT or doc.get("season") != 2026:
        raise ValueError("Unexpected experiment data: cannot overwrite")
    return doc


def comparison(log, season=2026, week=None):
    """Identical decisive games are graded for all four models."""
    selected = []
    for gid, snapshot in log.get("snapshots", {}).items():
        if snapshot.get("season") != season or (week is not None and snapshot.get("week") != week):
            continue
        result = log.get("results", {}).get(gid)
        if not result or result.get("winner_side") not in ("home", "away"):
            continue
        if set(snapshot.get("models", {})) != set(CHALLENGERS):
            continue
        selected.append((snapshot, result))
    rows = []
    for name in CHALLENGERS:
        errors = []
        losses = []
        confident = []
        for snapshot, result in selected:
            p = float(snapshot["models"][name]["home_win_probability"])
            true_home = int(result["winner_side"] == "home")
            correct = int((p >= .5) == bool(true_home))
            losses.append(correct)
            errors.append((p-true_home)**2)
            if max(p,1-p) >= .8:
                confident.append(correct)
        rows.append({
            "Model": name, "Graded": len(selected), "Wins": sum(losses),
            "Losses": len(selected)-sum(losses),
            "Accuracy": sum(losses)/len(selected) if selected else None,
            "Brier": sum(errors)/len(selected) if selected else None,
            "High confidence": len(confident),
            "High confidence wins": sum(confident),
            "High confidence accuracy": (
                sum(confident)/len(confident) if confident else None
            ),
        })
    return pd.DataFrame(rows)


def detail(log, season=2026, week=None):
    rows = []
    for gid, snapshot in log.get("snapshots", {}).items():
        if snapshot.get("season") != season or (week is not None and snapshot.get("week") != week):
            continue
        result = log.get("results", {}).get(gid, {})
        for name, pred in snapshot.get("models", {}).items():
            side = pred["predicted_side"]
            actual = result.get("winner_side")
            rows.append({
                "Week": snapshot["week"], "Game ID": gid,
                "Away": snapshot["away"], "Home": snapshot["home"],
                "Model": name, "Prediction": snapshot[side],
                "Win probability": pred["confidence"],
                "Captured (UTC)": snapshot["captured_at"],
                "Final": (f'{result["away_score"]:g}–{result["home_score"]:g}'
                          if actual else "Pending"),
                "Result": ("Pending" if not actual else "Tie" if actual == "tie"
                           else "Win" if side == actual else "Loss")
            })
    return pd.DataFrame(rows)


def show_comparison(st, season, week):
    with st.expander("Forward test · four model weight configurations", expanded=False):
        st.caption(
            "Prospective research only. All four probabilities are captured together "
            "before kickoff using identical earlier-week inputs, independently from "
            "the official Value Shortlist. Neither predictions nor tiers in the live "
            "app are changed. Historical games are not backfilled."
        )
        doc = load()
        if int(season) != 2026:
            st.info("Four-way prospective tracking started in 2026. Select the 2026 season.")
            return
        show_all = st.checkbox("Compare entire 2026 season", value=True,
                               key="prospective_weights_all_weeks")
        chosen_week = None if show_all else int(week)
        st.caption(
            "Checks are scheduled four times daily on GitHub Actions. "
            "A game is captured only if ESPN verifies that it is pregame within "
            "18 hours of kickoff. Missed captures aren't reconstructed. "
            f"Last checked (UTC): {doc.get('last_run') or 'No successful check yet'}."
        )
        total = sum(s.get("season") == int(season) and
                    (chosen_week is None or s.get("week") == chosen_week)
                    for s in doc["snapshots"].values())
        st.write(f"Locked same-game snapshots: **{total}**")
        summary = comparison(doc, season=int(season), week=chosen_week)
        if summary["Graded"].max() == 0:
            st.info("No verified final scores for locked four-way games yet.")
        else:
            display = summary.copy()
            for key in ("Accuracy", "High confidence accuracy"):
                display[key] = display[key].map(
                    lambda v: f"{v:.1%}" if pd.notna(v) else "—"
                )
            display["Brier"] = display["Brier"].map(
                lambda v: f"{v:.4f}" if pd.notna(v) else "—"
            )
            st.dataframe(display, use_container_width=True, hide_index=True)
            st.caption(
                "Accuracy counts straight-up winners, not ATS success. All four models "
                "share exactly the same graded games. Brier score is lower-is-better. "
                "Pending games and ties are excluded; no betting ROI is implied."
            )
        details = detail(doc, season=int(season), week=chosen_week)
        if not details.empty:
            with st.expander("Individual locked predictions"):
                st.dataframe(details, hide_index=True, use_container_width=True)
            st.download_button(
                "Export four-model prospective records · CSV",
                details.to_csv(index=False).encode("utf-8"),
                file_name="saturday_forecast_weight_challengers_2026.csv",
                mime="text/csv", key="prospective_weights_export",
            )
        else:
            st.caption("No eligible captures for this period yet.")
