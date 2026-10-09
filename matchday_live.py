"""Presentation-only scoreboard helpers for Saturday Live Mode.

Keep this separate from prediction and tier logic. It makes no network requests.
"""
from html import escape

import pandas as pd


LIVE_SECTIONS = ("Live", "Upcoming", "Final")


def live_board_rows(predictions, schedule):
    """Return existing matchup outcomes grouped live first, then upcoming, then final."""
    if predictions is None or predictions.empty:
        return []
    kickoff_by_id = {}
    if schedule is not None and not schedule.empty:
        for _, game in schedule.iterrows():
            game_id = pd.to_numeric(game.get("game_id"), errors="coerce")
            if pd.notna(game_id):
                kickoff_by_id[int(game_id)] = game.get("start_date")
    rows = []
    for _, pick in predictions.iterrows():
        game_id = pd.to_numeric(pick.get("Game ID"), errors="coerce")
        kickoff = pd.NaT
        if pd.notna(game_id):
            kickoff = pd.to_datetime(kickoff_by_id.get(int(game_id)), errors="coerce", utc=True)
        if pd.notna(kickoff):
            kickoff = kickoff.tz_convert("America/Chicago")
        kickoff_label = (
            kickoff.strftime("%a, %b %d · ") + kickoff.strftime("%I:%M %p").lstrip("0") + " CT"
            if pd.notna(kickoff) else "Kickoff TBD"
        )
        status = str(pick.get("Status", "Awaiting final"))
        section = ("Live" if status == "In progress" else
                   "Final" if status.startswith("Final") else "Upcoming")
        # Display only provider-reported scores, never estimated football scores.
        score = str(pick.get("Live Score", "—")) if section == "Live" else (
            str(pick.get("Final Score", "—")) if section == "Final" else "—"
        )
        if not score or score.lower() in ("nan", "none", "—"):
            score = ""
        detail = str(pick.get("Live Detail", ""))
        if detail.lower() in ("nan", "none"):
            detail = ""
        confidence = pd.to_numeric(pick.get("Confidence"), errors="coerce")
        tier = ""
        if bool(pick.get("Value Selected", False)):
            tier = str(pick.get("Value Tier", ""))
        result = str(pick.get("Pick Result", "Pending"))
        if result not in ("Correct", "Incorrect"):
            result = ""
        rows.append({
            "section": section,
            "status": status,
            "away": str(pick.get("Away Team", "")),
            "home": str(pick.get("Home Team", "")),
            "winner": str(pick.get("Predicted Winner", "")),
            "chance": f"{float(confidence):.1%}" if pd.notna(confidence) else "—",
            "kickoff": kickoff_label,
            "kickoff_timestamp": float(kickoff.timestamp()) if pd.notna(kickoff) else float("inf"),
            "detail": detail,
            "score": score,
            "tier": tier,
            "result": result,
        })
    order = {section: index for index, section in enumerate(LIVE_SECTIONS)}
    return sorted(rows, key=lambda row: (
        order[row["section"]], row["kickoff_timestamp"], row["away"], row["home"]
    ))


def live_board_html(rows):
    """Compact accessible scoreboard, escaping every source-derived label."""
    if not rows:
        return ""
    parts = ['<div class="live-board" aria-label="Game-day scoreboard">']
    for section in LIVE_SECTIONS:
        group = [item for item in rows if item["section"] == section]
        if not group:
            continue
        class_name = section.lower()
        parts.append(
            '<section class="live-board-group ' + class_name + '">'
            '<div class="live-board-section-heading"><h4>' + escape(section) + '</h4>'
            '<span>' + str(len(group)) + ' games</span></div>'
            '<div class="live-board-grid">'
        )
        for item in group:
            score_line = (
                '<div class="live-board-score">' + escape(item["score"]) + '</div>'
                if item["score"] else '<div class="live-board-no-score">Score unavailable</div>'
                if section != "Upcoming" else ""
            )
            status = (
                item["detail"] if section == "Live" and item["detail"] else
                "Final · awaiting verified score" if item["status"] != "Final" and section == "Final" else
                "Final" if section == "Final" else item["status"]
            )
            tier = '<span class="live-board-tier">' + escape(item["tier"]) + '</span>' if item["tier"] else ""
            result = (
                '<span class="live-board-outcome">' + escape(item["result"]) + ' pick</span>'
                if section == "Final" and item["result"] else ""
            )
            parts.append(
                '<article class="live-board-game">'
                '<div class="live-board-game-meta"><span>' + escape(item["kickoff"]) + '</span>'
                '<span class="live-board-game-state">' + escape(status) + '</span></div>'
                '<div class="live-board-matchup">' + escape(item["away"])
                + ' <span>at</span> ' + escape(item["home"]) + '</div>'
                + score_line
                + '<div class="live-board-pick">Pregame model pick: <strong>'
                + escape(item["winner"]) + '</strong> <span>· '
                + escape(item["chance"]) + ' estimated chance</span></div>'
                '<div class="live-board-tags">' + tier + result + '</div>'
                '</article>'
            )
        parts.append('</div></section>')
    return "".join(parts) + '</div>'
