from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from html import escape
from html.parser import HTMLParser
import re
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import math
from itertools import combinations
from heapq import nlargest
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import HTTPError
from io import BytesIO
import base64
import pandas as pd
import numpy as np
import streamlit as st
import streamlit.components.v1 as components
# Reload the release module so a warm Streamlit process picks up waterfall functions.
import importlib
import model_v1_5
importlib.reload(model_v1_5)
from model_v1_5 import MODEL_VERSION, COMPONENT_SPEC, predict_week, add_waterfall_value, waterfall_scenario_rows
from bet_tracker_ui import show_bet_tracker
import importlib
import matchup_advantages
# Streamlit may retain imported modules after a source-only deployment.
importlib.reload(matchup_advantages)
from matchup_advantages import (build_advantages, advantage_html, assess, normalize_fbs_schedule,
                                build_waterfall_profiles, weather_tier_candidate_ids)
from shadow_tracking import show_shadow_tracking
from weather_context import build_weather_context
from live_scores import parse_live_scores, overlay_live_scores

st.set_page_config(page_title="Saturday Forecast", page_icon="assets/cfb_icon.svg", layout="wide", initial_sidebar_state="collapsed")

# Theme Streamlit 1.64's running indicator before loading any matchup data.
# Keep its native visibility, accessible label, and adjacent Stop control.
st.markdown("""
<style>
[data-testid="stStatusWidgetRunningIcon"] {
    position: relative;
}
[data-testid="stStatusWidgetRunningIcon"] > svg,
[data-testid="stStatusWidgetRunningIcon"] > img {
    visibility: hidden;
}
[data-testid="stStatusWidgetRunningIcon"]::after {
    content: "🏈";
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.65rem;
    line-height: 1;
    pointer-events: none;
    animation: cfb-loading-football 1.2s ease-in-out infinite;
}
@keyframes cfb-loading-football {
    0%, 100% { transform: translateY(0) rotate(-25deg); }
    50% { transform: translateY(-3px) rotate(25deg); }
}
@media (prefers-reduced-motion: reduce) {
    [data-testid="stStatusWidgetRunningIcon"]::after { animation: none; }
}
</style>
""", unsafe_allow_html=True)




TOUR_STEPS = [
    ("schedule", None, "Choose your games", "Choose Season and Week just below. Kickoff times use Central Time with AM/PM. Only regular-season FBS vs. FBS matchups are included."),
    ("filters", "Game cards", "Find your teams", "Search a team, choose favorites, or narrow the confidence and game-status filters below. Reset filters brings back the full slate."),
    ("cards", "Game cards", "Read a game card", "The cards below show predicted winners, win probabilities, available moneylines and spreads, expected game-window weather, and live or final scores. Confidence is an estimate, not a guarantee."),
    ("risky", "Risky picks", "Review matchup warnings", "This tab lists non-tiered predicted winners below 80% model confidence with two or fewer of the five matchup advantages for the selected week. Official Tier 1–5 games and High/Very High confidence picks are excluded so the labels do not contradict each other. Missing data is shown separately."),
    ("export", None, "Export your picks", "Use Export picks above the navigation to download all picks for this week or only the picks matching your Game cards filters. Open the CSV in Excel to compare matchups."),
    ("results", "Model results", "Check model performance", "Compare model wins, losses, and accuracy by confidence, plus Value Pick records overall and by tier. Value Pick tracking starts in Week 3; Weeks 1 and 2 are excluded from the tier record."),
    ("scenario", "What-if bets", "Try a betting scenario", "Choose picks and stakes below to see potential profit if they win and the amount lost if they lose. Missing moneylines are excluded. A scenario does not place or record bets."),
    ("parlay", "Parlay finder", "Build a parlay", "The finder is open below. Choose 2–5 legs, your stake, minimum confidence, and ranking: win probability, payout, or estimated value. It uses future games with available lines from one sportsbook. Payouts are estimates, and joint win chances assume independent outcomes. If there are too few eligible games, try another week or broader filters."),
    ("tracker", "My bets", "Track your actual bets", "Record the team, actual odds, and stake you placed. Backup and restore imports saved singles and supported moneyline parlays. Records stay in this browser, so download a backup before switching devices or clearing storage."),
]


def set_tour_step(step):
    previous = st.session_state.get("app_tour_step")
    if step is not None and 0 <= step < len(TOUR_STEPS):
        if previous is None or previous == -1:
            st.session_state["tour_parlay_original"] = st.session_state.get("parlay_enabled", False)
        tab = TOUR_STEPS[step][1]
        if tab:
            st.session_state["main_app_tabs"] = tab
        if TOUR_STEPS[step][0] == "parlay":
            st.session_state["parlay_enabled"] = True
    elif step is None and "tour_parlay_original" in st.session_state:
        st.session_state["parlay_enabled"] = st.session_state.pop("tour_parlay_original")
    st.session_state["app_tour_step"] = step
    st.session_state["tour_scroll_token"] = str(datetime.now(timezone.utc).timestamp())


def show_app_tour():
    """Offer the tour at the top; render active controls beside their target."""
    step = st.session_state.get("app_tour_step", -1)
    if step == -1:
        with st.container(border=True):
            st.markdown("**Welcome! Would you like a quick tour?**")
            st.caption("We will open each section and guide you through it.")
            start, skip = st.columns(2)
            start.button("Take the tour", on_click=set_tour_step, args=(0,), key="tour_start")
            skip.button("Not now", on_click=set_tour_step, args=(None,), key="tour_skip")
    elif step is None:
        st.button("Take the app tour", on_click=set_tour_step, args=(0,), key="tour_replay")
    else:
        resume, stop = st.columns(2)
        resume.button("Resume current tour step", on_click=set_tour_step, args=(step,), key="tour_resume")
        stop.button("End tour", on_click=set_tour_step, args=(None,), key="tour_end")
    st.caption("Tour preference is remembered for this session.")


def tour_at(target):
    step = st.session_state.get("app_tour_step")
    if not isinstance(step, int) or not 0 <= step < len(TOUR_STEPS):
        return
    name, tab, title, body = TOUR_STEPS[step]
    if name != target:
        return
    anchor = "cfb-tour-" + target
    st.markdown(f'<div id="{anchor}" style="scroll-margin-top:5rem"></div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.caption(f"App tour · Step {step + 1} of {len(TOUR_STEPS)}")
        st.progress((step + 1) / len(TOUR_STEPS))
        st.markdown(f"**{title}**")
        st.write(body)
        back, forward, close = st.columns(3)
        back.button("Back", disabled=step == 0, on_click=set_tour_step, args=(step - 1,), key="tour_back")
        forward.button("Finish" if step == len(TOUR_STEPS) - 1 else "Next",
                       on_click=set_tour_step,
                       args=(None if step == len(TOUR_STEPS) - 1 else step + 1,), key="tour_next")
        close.button("Skip tour", on_click=set_tour_step, args=(None,), key="tour_close")
        st.markdown(f"[Jump to this tour step](#{anchor})")
    # Wait for the selected tab and its target to become visible. The token
    # prevents score refreshes and unrelated controls from stealing scroll.
    config = json.dumps({"anchor": anchor, "token": st.session_state.get("tour_scroll_token", "")})
    components.html("""
<script>
const config = """ + config + """;
let attempts = 0;
const timer = setInterval(() => {
  if (++attempts > 80) { clearInterval(timer); return; }
  try {
    const doc = window.parent.document;
    const node = doc.getElementById(config.anchor);
    if (!node || !node.getClientRects().length) return;
    if (window.parent.__cfbTourScrollToken === config.token) {
      clearInterval(timer); return;
    }
    window.parent.__cfbTourScrollToken = config.token;
    node.scrollIntoView({behavior: "smooth", block: "start"});
    clearInterval(timer);
  } catch (_) { clearInterval(timer); }
}, 100);
window.addEventListener("pagehide", () => clearInterval(timer));
</script>
""", height=0)


def confidence_performance(frame):
    """Grade only final decisive games, using the unrounded pick probability."""
    confidence = pd.to_numeric(frame["Confidence"], errors="coerce")
    bands = [
        ("Very high · 90%+", .9, float("inf")),
        ("High · 80–90%", .8, .9),
        ("Moderate · 70–80%", .7, .8),
        ("Lean · 60–70%", .6, .7),
        ("Toss-up · under 60%", 0, .6),
    ]
    rows = []
    for label, low, high in bands:
        group = frame[confidence.ge(low) & confidence.lt(high)]
        graded = group[group["Status"].eq("Final") & group["Pick Result"].isin(["Correct", "Incorrect"])]
        wins = int(graded["Pick Result"].eq("Correct").sum())
        n = len(graded)
        rows.append({
            "Confidence level": label, "Picks": len(group), "Graded": n,
            "Wins": wins, "Losses": n - wins,
            "Accuracy": wins / n if n else None,
            "Average model confidence": pd.to_numeric(graded["Confidence"], errors="coerce").mean() if n else None,
            "Awaiting final": int(group["Status"].ne("Final").sum()),
            "Not graded": int((group["Status"].eq("Final") & ~group["Pick Result"].isin(["Correct", "Incorrect"])).sum()),
        })
    return pd.DataFrame(rows)


def should_flag_risky(scored, value_selected, confidence):
    """Risk warnings apply only to non-tiered picks below 80% model confidence."""
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        return False
    return bool(
        scored is not None
        and scored.get("flag")
        and not bool(value_selected)
        and np.isfinite(confidence)
        and confidence < 0.80
    )


def value_pick_performance(frame):
    """Summarize official Value Picks from Week 3 onward."""
    columns = [
        "Tier", "Picks", "Graded", "Wins", "Losses", "Pushes",
        "Win rate", "Awaiting final", "Not graded",
    ]
    if frame is None or frame.empty or "Value Selected" not in frame:
        return pd.DataFrame(columns=columns)
    work = frame.copy()
    weeks = pd.to_numeric(work.get("Week"), errors="coerce")
    work = work[weeks.ge(3) & work["Value Selected"].fillna(False).astype(bool)]
    if work.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    groups = [("All value picks", work)]
    if "Value Stage" in work:
        stages = pd.to_numeric(work["Value Stage"], errors="coerce")
        for stage in (1, 2, 3, 4, 5):
            group = work[stages.eq(stage)]
            if group.empty:
                continue
            tier_name = str(group["Value Tier"].iloc[0]) if "Value Tier" in group else f"Tier {stage}"
            groups.append((tier_name, group))

    for label, group in groups:
        result = group.get("Value Result", pd.Series("Pending", index=group.index)).astype(str)
        wins = int(result.eq("Correct").sum())
        losses = int(result.eq("Incorrect").sum())
        pushes = int(result.eq("Push").sum())
        graded = wins + losses + pushes
        rows.append({
            "Tier": label,
            "Picks": len(group),
            "Graded": graded,
            "Wins": wins,
            "Losses": losses,
            "Pushes": pushes,
            "Win rate": wins / (wins + losses) if wins + losses else None,
            "Awaiting final": int(result.eq("Pending").sum()),
            "Not graded": int(result.eq("Not graded").sum()),
        })
    return pd.DataFrame(rows, columns=columns)


@st.cache_data(ttl=300)
def download_schedule(season):
    url = f"https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{season}.csv"
    with urlopen(url, timeout=30) as response:
        frame = pd.read_csv(BytesIO(response.read()), low_memory=False)
        frame.attrs["fetched_at"] = datetime.now(ZoneInfo("America/Chicago")).strftime("%b %d, %I:%M %p %Z")
        return frame

@st.cache_data(ttl=3600, show_spinner=False)
def download_summary(year):
    url = (
        "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"
        f"cfb_team_summaries_weekly/cfb_team_summaries_weekly_{year}.csv"
    )
    with urlopen(url, timeout=60) as response:
        frame = pd.read_csv(BytesIO(response.read()), low_memory=False)
        frame.attrs["fetched_at"] = datetime.now(ZoneInfo("America/Chicago")).strftime("%b %d, %I:%M %p %Z")
        return frame


@st.cache_data(ttl=900, show_spinner=False)
def value_weather_context(schedule_frame, week, candidate_ids):
    return build_weather_context(schedule_frame, week, candidate_ids)


def read_summary(upload, year):
    if upload is not None:
        frame = pd.read_csv(upload, low_memory=False)
    else:
        frame = download_summary(year).copy()
    required = {"season", "team_id", "through_week"} | {spec[0] for spec in COMPONENT_SPEC.values()}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{year} summaries are missing: " + ", ".join(sorted(missing)))
    frame = frame[pd.to_numeric(frame["season"], errors="coerce") == year].copy()
    for col in required - {"season"}:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    if frame.empty:
        raise ValueError(f"No team-summary data for {year} has been published yet.")
    if frame[["team_id", "through_week"]].isna().any().any():
        raise ValueError(f"{year} summaries contain invalid team IDs or weeks.")
    if frame.duplicated(["team_id", "through_week"]).any():
        raise ValueError(f"{year} summaries contain duplicate team/week rows.")
    return frame


def augment_missing_summaries(current, prior, schedule, target_week):
    """Create transparent provisional rows when the weekly feed omits a team.

    The schedule has reliable completed-game scores even when the advanced
    summary release is late. Clone the team's latest prior-season profile and
    apply a modest scoring/points-allowed adjustment from completed games.
    """
    result = current.copy()
    derived = {}
    eligible_ids = set(result.loc[pd.to_numeric(result["through_week"], errors="coerce") < int(target_week), "team_id"].astype(int))
    games = schedule.copy()
    if "completed" in games:
        done = games["completed"].astype(str).str.lower().isin(["true", "t", "1", "1.0", "yes", "y"])
        games = games[done]
    games = games[pd.to_numeric(games["week"], errors="coerce") < int(target_week)]
    games = games[pd.notna(games["home_points"]) & pd.notna(games["away_points"])]
    if games.empty:
        return result, derived
    for tid in set(games["home_id"].astype(int)) | set(games["away_id"].astype(int)):
        if tid in eligible_ids:
            continue
        prior_rows = prior[prior["team_id"].astype(int) == tid]
        team_games = games[(games["home_id"].astype(int) == tid) | (games["away_id"].astype(int) == tid)]
        if prior_rows.empty or team_games.empty:
            continue
        base = prior_rows.sort_values("through_week").iloc[-1].copy()
        points_for, points_against = [], []
        for _, game in team_games.iterrows():
            if int(game["home_id"]) == tid:
                points_for.append(float(game["home_points"]))
                points_against.append(float(game["away_points"]))
            else:
                points_for.append(float(game["away_points"]))
                points_against.append(float(game["home_points"]))
        # Keep the adjustment deliberately conservative; it supplements the
        # prior profile rather than pretending a full advanced-stat snapshot.
        base["season"] = int(pd.to_numeric(schedule["season"], errors="coerce").dropna().iloc[0])
        base["through_week"] = int(pd.to_numeric(team_games["week"], errors="coerce").max())
        if "adj_off_epa" in base:
            base["adj_off_epa"] = float(base["adj_off_epa"]) + (sum(points_for) / len(points_for) - 28.0) / 14.0
        if "adj_def_epa" in base:
            base["adj_def_epa"] = float(base["adj_def_epa"]) + (sum(points_against) / len(points_against) - 28.0) / 14.0
        result = pd.concat([result, pd.DataFrame([base])], ignore_index=True)
        derived[tid] = {"games": len(team_games), "through_week": int(base["through_week"])}
    return result, derived

def predict_all_games(current, prior, schedule, week):
    # Preserve prior-week results for venue history; include every target-week game.
    model_schedule = schedule.copy()
    target = pd.to_numeric(model_schedule["week"], errors="coerce") == int(week)
    if "completed" in model_schedule:
        model_schedule.loc[target, "completed"] = False
    predictions = predict_week(current, prior, model_schedule, week)
    if not predictions.empty and "Game ID" not in predictions:
        predictions["Game ID"] = None
    return predictions


def attach_results(predictions, games):
    outcomes = games.copy()
    completed = outcomes.get("completed", pd.Series(False, index=outcomes.index)).astype(str).str.lower().isin(["true", "t", "1", "1.0", "yes", "y"])
    for col, default in [("Live State", ""), ("Live Detail", ""), ("Live Score", "—")]:
        if col not in outcomes:
            outcomes[col] = default
    outcomes["Status"] = "Awaiting final"
    outcomes.loc[outcomes["Live State"].eq("in") & ~completed, "Status"] = "In progress"
    outcomes.loc[completed, "Status"] = "Final · score pending"
    valid = completed & outcomes["home_points"].notna() & outcomes["away_points"].notna()
    outcomes.loc[valid, "Status"] = "Final"
    outcomes["Actual Winner"] = "—"
    outcomes.loc[valid & (outcomes.home_points > outcomes.away_points), "Actual Winner"] = outcomes["home_team"]
    outcomes.loc[valid & (outcomes.home_points < outcomes.away_points), "Actual Winner"] = outcomes["away_team"]
    outcomes.loc[valid & (outcomes.home_points == outcomes.away_points), "Actual Winner"] = "Tie"
    outcomes["Final Score"] = "—"
    for i in outcomes.index[valid]:
        outcomes.loc[i, "Final Score"] = f"{outcomes.loc[i, 'away_team']} {outcomes.loc[i, 'away_points']:g} – {outcomes.loc[i, 'home_team']} {outcomes.loc[i, 'home_points']:g}"
    outcomes = outcomes.rename(columns={"game_id": "Game ID", "home_team": "Home Team", "away_team": "Away Team"})
    keys = ["Game ID"] if "Game ID" in outcomes and predictions["Game ID"].notna().all() else ["Home Team", "Away Team"]
    result = predictions.merge(outcomes[keys + ["Status", "Actual Winner", "Final Score", "Live State", "Live Detail", "Live Score"]], on=keys, how="left", validate="one_to_one")
    result["Pick Result"] = "Pending"
    scored = result["Status"].eq("Final") & result["Actual Winner"].ne("Tie")
    result.loc[scored, "Pick Result"] = "Incorrect"
    result.loc[scored & result["Predicted Winner"].eq(result["Actual Winner"]), "Pick Result"] = "Correct"
    result.loc[result["Actual Winner"].eq("Tie"), "Pick Result"] = "Not graded"
    return result


def format_moneyline(value):
    if value is None or isinstance(value, bool):
        return "Unavailable"
    raw = str(value).strip().replace("−", "-")
    if raw.upper() in {"EVEN", "EV", "EVS"}:
        return "+100"
    try:
        price = float(raw)
        if not math.isfinite(price) or abs(price) < 100 or not price.is_integer():
            return "Unavailable"
        return f"{int(price):+d}"
    except (ValueError, TypeError):
        return "Unavailable"


def format_spread(value):
    if value is None or isinstance(value, bool):
        return "Unavailable"
    raw = str(value).strip().replace("−", "-").replace(" ", "")
    if raw.upper() in {"PK", "PICK", "PICKEM", "PICK'EM"}:
        return "+0"
    try:
        number = float(raw.replace("+", ""))
        if not math.isfinite(number) or abs(number) > 100:
            return "Unavailable"
        return f"{int(number):+d}" if number.is_integer() else f"{number:+.1f}"
    except (ValueError, TypeError):
        return "Unavailable"


def parse_draftkings(payload):
    """Return each sportsbook's current moneyline and point spread for each event."""
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise ValueError("Invalid odds response")
    quotes = {}
    for event in payload["events"]:
        event_quotes = {}
        for competition in event.get("competitions", []):
            sides = {x.get("homeAway"): str(x.get("team", {}).get("id", "")) for x in competition.get("competitors", [])}
            completed = bool(competition.get("status", {}).get("type", {}).get("completed", False))
            for odds in competition.get("odds", []):
                provider_name = str(odds.get("provider", {}).get("name", "")).strip()
                if not provider_name:
                    continue
                prices = {}
                for side in ("home", "away"):
                    ml_market = odds.get("moneyline", {}).get(side, {})
                    ml_close = (ml_market.get("close") or {}).get("odds")
                    if ml_close is None:
                        ml_close = odds.get(side + "TeamOdds", {}).get("moneyLine")
                    prices[side] = format_moneyline(ml_close)
                    ml_open = (ml_market.get("open") or {}).get("odds")
                    if ml_open is None:
                        legacy = (odds.get(side + "TeamOdds", {}).get("open") or {}).get("moneyLine", {})
                        ml_open = legacy.get("american", legacy.get("alternateDisplayValue")) if isinstance(legacy, dict) else legacy
                    prices[side + "_open"] = format_moneyline(ml_open)

                    spread_market = odds.get("pointSpread", {}).get(side, {})
                    spread_close = (spread_market.get("close") or {}).get("line")
                    spread_price = (spread_market.get("close") or {}).get("odds")
                    spread_open = (spread_market.get("open") or {}).get("line")
                    spread_open_price = (spread_market.get("open") or {}).get("odds")
                    if spread_close is None and odds.get("spread") is not None:
                        try:
                            home_spread = float(odds.get("spread"))
                            spread_close = home_spread if side == "home" else -home_spread
                        except (TypeError, ValueError):
                            pass
                    if spread_price is None:
                        spread_price = odds.get(side + "TeamOdds", {}).get("spreadOdds")
                    prices[side + "_spread"] = format_spread(spread_close)
                    prices[side + "_spread_odds"] = format_moneyline(spread_price)
                    prices[side + "_spread_open"] = format_spread(spread_open)
                    prices[side + "_spread_open_odds"] = format_moneyline(spread_open_price)

                if all(prices[k] == "Unavailable" for k in ("home", "away", "home_spread", "away_spread")):
                    continue
                event_quotes[provider_name] = {
                    "home_id": sides.get("home", ""), "away_id": sides.get("away", ""),
                    "home": prices["home"], "away": prices["away"], "completed": completed,
                    "home_open": prices["home_open"], "away_open": prices["away_open"],
                    "home_spread": prices["home_spread"], "away_spread": prices["away_spread"],
                    "home_spread_odds": prices["home_spread_odds"], "away_spread_odds": prices["away_spread_odds"],
                    "home_spread_open": prices["home_spread_open"], "away_spread_open": prices["away_spread_open"],
                    "home_spread_open_odds": prices["home_spread_open_odds"], "away_spread_open_odds": prices["away_spread_open_odds"],
                }
        if event_quotes:
            quotes[str(event.get("id"))] = event_quotes
    return quotes

def parse_archived_summary(payload, event_id):
    header = payload.get("header", {})
    if str(header.get("id")) != str(event_id):
        return {}
    competitions = []
    for competition in header.get("competitions", []):
        if not competition.get("status", {}).get("type", {}).get("completed", False):
            continue
        archived = dict(competition)
        archived["odds"] = payload.get("pickcenter", [])
        competitions.append(archived)
    return parse_draftkings({"events": [{"id": str(event_id), "competitions": competitions}]}).get(str(event_id), {})


@st.cache_data(ttl=86400, show_spinner=False)
def download_archived_event(event_id, movement_schema=1):
    if not str(event_id).isdigit():
        return {}
    url = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event=" + str(event_id)
    with urlopen(url, timeout=15) as response:
        return parse_archived_summary(json.load(response), event_id)


def fetch_scoreboard(date_range):
    """Retry rejected date ranges as daily requests, retaining event IDs."""
    def fetch_day(dates):
        query = urlencode({"dates": dates, "groups": 80, "limit": 1000})
        url = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?" + query
        with urlopen(url, timeout=20) as response:
            payload = json.load(response)
        if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
            raise ValueError("Invalid scoreboard response")
        return payload
    try:
        return fetch_day(date_range)
    except HTTPError as exc:
        if exc.code != 400 or "-" not in date_range:
            raise
    start, end = date_range.split("-", 1)
    dates = pd.date_range(datetime.strptime(start, "%Y%m%d"), datetime.strptime(end, "%Y%m%d"))
    if not 1 <= len(dates) <= 31:
        raise ValueError("Odds date range must cover 1–31 days")
    events = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for payload in pool.map(fetch_day, dates.strftime("%Y%m%d").tolist()):
            for event in payload["events"]:
                events[str(event["id"])] = event
    return {"events": list(events.values())}


@st.cache_data(ttl=60, show_spinner=False)
def download_live_event(event_id):
    """Read an omitted game's official status; never infer final from kickoff."""
    if not str(event_id).isdigit():
        return {}
    url = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event=" + str(event_id)
    with urlopen(url, timeout=15) as response:
        payload = json.load(response)
    header = payload.get("header", {})
    if str(header.get("id")) != str(event_id):
        raise ValueError("Game summary identity mismatch")
    return parse_live_scores({"events": [header]})


@st.cache_data(ttl=60, show_spinner=False)
def download_live_scores(date_range, event_ids=()):
    # A successful scoreboard response can still omit games. Reconcile against
    # the selected schedule, not the number of events returned by the feed.
    errors = []
    try:
        scores = parse_live_scores(fetch_scoreboard(date_range))
    except Exception:
        if not event_ids:
            raise
        scores = {}
    missing = [str(event_id) for event_id in event_ids if str(event_id) not in scores]
    def fetch_missing(event_id):
        try:
            return event_id, download_live_event(event_id)
        except Exception:
            return event_id, {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for event_id, extra in pool.map(fetch_missing, missing):
            if event_id not in extra:
                errors.append(event_id)
            scores.update(extra)
    return {"games": scores, "missing_event_ids": errors,
            "retrieved": datetime.now(ZoneInfo("America/Chicago")).strftime("%b %d, %I:%M:%S %p %Z")}


@st.cache_data(ttl=300, show_spinner=False)
def download_event_moneylines(event_id, movement_schema=1):
    """Read current per-game markets, including games omitted by the scoreboard."""
    if not str(event_id).isdigit():
        return {}
    url = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event=" + str(event_id)
    with urlopen(url, timeout=15) as response:
        payload = json.load(response)
    header = payload.get("header", {})
    if str(header.get("id")) != str(event_id):
        raise ValueError("Odds event ID does not match the requested game")
    competitions = []
    for competition in header.get("competitions", []):
        entry = dict(competition)
        entry["odds"] = payload.get("pickcenter", []) or competition.get("odds", [])
        competitions.append(entry)
    return parse_draftkings({"events": [{"id": str(event_id), "competitions": competitions}]}).get(str(event_id), {})


def schedule_event_ids(games):
    return tuple(sorted({str(int(value)) for value in games.get("game_id", pd.Series(dtype=float)).dropna()}))


@st.cache_data(ttl=300, show_spinner=False)
def download_market_odds(date_range, event_ids=()):
    payload = fetch_scoreboard(date_range)
    quotes = parse_draftkings(payload)
    archive_path = Path(__file__).parent / "data" / "archived_moneylines_2026.json"
    try:
        saved = json.loads(archive_path.read_text()).get("events", {}) if archive_path.exists() else {}
    except (OSError, ValueError):
        saved = {}
    missing = []
    for event in payload.get("events", []):
        event_id = str(event.get("id"))
        completed = any(c.get("status", {}).get("type", {}).get("completed", False) for c in event.get("competitions", []))
        if not completed or event_id in quotes:
            continue
        stored = saved.get(event_id, {}).get("quotes", {})
        if stored:
            quotes[event_id] = stored
        elif event_id.isdigit():
            missing.append(event_id)
    # ESPN's weekly scoreboard omits completed-game prices. Retrieve each
    # missing game's archived summary, with a daily per-event cache.
    def get_archive(event_id):
        try:
            return event_id, download_archived_event(event_id)
        except Exception:
            return event_id, {}
    if missing:
        with ThreadPoolExecutor(max_workers=6) as pool:
            for event_id, archived in pool.map(get_archive, missing):
                if archived:
                    quotes[event_id] = archived
    # Probe every scheduled game with missing/partial DK prices, even when it
    # was omitted by the weekly scoreboard. Per-event lookups expire in 5 minutes.
    expected = set(event_ids) | {str(e.get("id")) for e in payload.get("events", [])}
    targets = []
    for event_id in expected:
        dk = next((q for name, q in quotes.get(event_id, {}).items()
                   if name.lower().replace(" ", "") == "draftkings"), {})
        if any(dk.get(k, "Unavailable") == "Unavailable" for k in ("home", "away", "home_open", "away_open", "home_spread", "away_spread")):
            targets.append(event_id)
    lookup_errors = []
    def get_current(event_id):
        try:
            return event_id, download_event_moneylines(event_id), False
        except Exception:
            return event_id, {}, True
    with ThreadPoolExecutor(max_workers=6) as pool:
        for event_id, extra, failed in pool.map(get_current, targets):
            if failed:
                lookup_errors.append(event_id)
            providers = quotes.setdefault(event_id, {})
            for name, quote in extra.items():
                previous = providers.get(name)
                if previous is None:
                    providers[name] = quote
                elif (previous.get("home_id"), previous.get("away_id")) == (quote.get("home_id"), quote.get("away_id")):
                    for side in ("home", "away", "home_open", "away_open",
                                 "home_spread", "away_spread", "home_spread_odds", "away_spread_odds",
                                 "home_spread_open", "away_spread_open",
                                 "home_spread_open_odds", "away_spread_open_odds"):
                        if previous.get(side, "Unavailable") == "Unavailable":
                            previous[side] = quote.get(side, "Unavailable")
    return {"quotes": quotes, "lookup_errors": lookup_errors,
            "retrieved": datetime.now(ZoneInfo("America/Chicago")).strftime("%b %d, %I:%M %p %Z")}


def attach_odds(predictions, games, quotes):
    result = predictions.copy()
    defaults = {
        "DK Away ML": "Unavailable", "DK Home ML": "Unavailable",
        "Away ML": "Unavailable", "Home ML": "Unavailable", "ML Source": "Unavailable",
        "DK Away Spread": "Unavailable", "DK Home Spread": "Unavailable",
        "Away Spread": "Unavailable", "Home Spread": "Unavailable", "Spread Source": "Unavailable",
        "Away Spread Odds": "Unavailable", "Home Spread Odds": "Unavailable",
        "Away Opening Spread": "Unavailable", "Home Opening Spread": "Unavailable",
        "Odds Type": "Not offered / unavailable",
        "Away Opening ML": "Unavailable", "Home Opening ML": "Unavailable",
    }
    for col, default in defaults.items():
        result[col] = default

    for index, row in result.iterrows():
        match = games[(games.home_team == row["Home Team"]) & (games.away_team == row["Away Team"])]
        if len(match) != 1 or "game_id" not in match:
            continue
        game = match.iloc[0]
        if pd.isna(game.game_id):
            continue
        event_quotes = quotes.get(str(int(game.game_id)), {})
        if not isinstance(event_quotes, dict):
            continue
        if "home_id" in event_quotes and "away_id" in event_quotes:
            event_quotes = {"DraftKings": event_quotes}
        valid = {}
        for provider, quote in event_quotes.items():
            if not isinstance(quote, dict):
                continue
            try:
                home_id = str(int(game["home_id"]))
                away_id = str(int(game["away_id"]))
            except (TypeError, ValueError, OverflowError):
                continue
            if quote.get("home_id") == home_id and quote.get("away_id") == away_id:
                valid[provider] = quote
        if not valid:
            continue

        dk_name = next((name for name in valid if name.lower().replace(" ", "") == "draftkings"), None)
        dk = valid.get(dk_name) if dk_name else None
        if dk:
            result.loc[index, "DK Away ML"] = dk.get("away", "Unavailable")
            result.loc[index, "DK Home ML"] = dk.get("home", "Unavailable")
            result.loc[index, "DK Away Spread"] = dk.get("away_spread", "Unavailable")
            result.loc[index, "DK Home Spread"] = dk.get("home_spread", "Unavailable")

        predicted_side = "home" if row["Predicted Side"] == "Home" else "away"
        ml_choices = [(name, quote) for name, quote in valid.items()
                      if quote.get(predicted_side, "Unavailable") != "Unavailable"]
        if dk and dk.get(predicted_side, "Unavailable") != "Unavailable":
            ml_name, ml_quote = dk_name, dk
        elif ml_choices:
            ml_name, ml_quote = ml_choices[0]
        else:
            ml_name, ml_quote = None, None
        if ml_quote is not None:
            result.loc[index, "Away ML"] = ml_quote.get("away", "Unavailable")
            result.loc[index, "Home ML"] = ml_quote.get("home", "Unavailable")
            result.loc[index, "ML Source"] = ml_name
            result.loc[index, "Away Opening ML"] = ml_quote.get("away_open", "Unavailable")
            result.loc[index, "Home Opening ML"] = ml_quote.get("home_open", "Unavailable")

        spread_choices = [(name, quote) for name, quote in valid.items()
                          if quote.get("home_spread", "Unavailable") != "Unavailable"
                          and quote.get("away_spread", "Unavailable") != "Unavailable"]
        if dk and dk.get("home_spread", "Unavailable") != "Unavailable" and dk.get("away_spread", "Unavailable") != "Unavailable":
            spread_name, spread_quote = dk_name, dk
        elif spread_choices:
            spread_name, spread_quote = spread_choices[0]
        else:
            spread_name, spread_quote = None, None
        if spread_quote is not None:
            result.loc[index, "Away Spread"] = spread_quote.get("away_spread", "Unavailable")
            result.loc[index, "Home Spread"] = spread_quote.get("home_spread", "Unavailable")
            result.loc[index, "Spread Source"] = spread_name
            result.loc[index, "Away Spread Odds"] = spread_quote.get("away_spread_odds", "Unavailable")
            result.loc[index, "Home Spread Odds"] = spread_quote.get("home_spread_odds", "Unavailable")
            result.loc[index, "Away Opening Spread"] = spread_quote.get("away_spread_open", "Unavailable")
            result.loc[index, "Home Opening Spread"] = spread_quote.get("home_spread_open", "Unavailable")

        completed = bool((ml_quote or spread_quote or {}).get("completed", False))
        result.loc[index, "Odds Type"] = "Archived line" if completed or str(row["Status"]).startswith("Final") else "Latest available line"
    return result

def moneyline_probability(line):
    formatted = format_moneyline(line)
    if formatted == "Unavailable":
        return None
    n = float(formatted)
    return 100 / (n + 100) if n > 0 else -n / (-n + 100)


def line_movement_html(row, history, observed_at):
    """Opening comparisons plus same-book session observations, never mixed books."""
    book = str(row.get("ML Source", "Unavailable"))
    if book == "Unavailable":
        return ""
    event = str(row.get("Game ID", ""))
    valid_event = event not in ("", "None", "nan")
    notes, session_notes = [], []
    comparable = 0
    moved = False
    for side in ("Away", "Home"):
        current = format_moneyline(row.get(side + " ML"))
        opening = format_moneyline(row.get(side + " Opening ML"))
        team = str(row[side + " Team"])
        if current == "Unavailable":
            continue
        if opening != "Unavailable":
            comparable += 1
            if moneyline_probability(current) != moneyline_probability(opening):
                moved = True
                direction = "shortened" if moneyline_probability(current) > moneyline_probability(opening) else "lengthened"
                notes.append(f"{escape(team)}: {escape(opening)} → {escape(current)} ({direction})")
        if valid_event and observed_at:
            key = (event, book.casefold().replace(" ", ""), side)
            old = history.get(key)
            if old and moneyline_probability(old["line"]) != moneyline_probability(current):
                old = {"line": current, "previous": old["line"], "changed": observed_at}
            elif old is None:
                old = {"line": current, "previous": None, "changed": None}
            history[key] = old
            if old["previous"] is not None:
                moved = True
                session_notes.append(f"{escape(team)}: {escape(old['previous'])} → {escape(current)} · observed {escape(old['changed'])}")
    if not moved:
        message = "No net movement from opening" if comparable == 2 else "Partial opening history; no movement detected on available side" if comparable else "Opening-line history unavailable"
        return '<div class="venue-label" style="margin-top:8px">' + message + '</div>'
    title = "Archived moneyline movement" if str(row.get("Status", "")).startswith("Final") else "Live moneyline movement" if row.get("Status") == "In progress" else "Moneyline moved"
    body = ""
    if notes:
        body += "<div><strong>Opening → latest</strong><br>" + "<br>".join(notes) + "</div>"
    if session_notes:
        body += "<div style='margin-top:6px'><strong>Last change observed this session</strong><br>" + "<br>".join(session_notes) + "</div>"
    if not notes and not comparable:
        body += "<div>Opening history unavailable.</div>"
    stamp = f"<div style='margin-top:6px'>As of {escape(observed_at)}</div>" if observed_at else ""
    return f'<details style="margin-top:10px;border-left:3px solid #d89c39;padding-left:10px"><summary style="cursor:pointer"><strong>↔ {title}</strong></summary><div class="venue-label">{escape(book)}{body}{stamp}</div></details>'


def add_betting_value(predictions):
    """Add market-implied probability and model value for the selected side."""
    result = predictions.copy()
    result["Bet Line"] = result.apply(
        lambda row: row["Home ML"] if row["Predicted Side"] == "Home" else row["Away ML"], axis=1
    )
    line = pd.to_numeric(result["Bet Line"].astype(str).str.replace("+", "", regex=False), errors="coerce")
    result["Market Implied %"] = np.where(line > 0, 100 / (line + 100), -line / (-line + 100))
    result.loc[line.isna(), "Market Implied %"] = np.nan
    result["Model Edge"] = result["Confidence"] - result["Market Implied %"]
    result["Expected Value"] = np.where(
        line > 0,
        result["Confidence"] * (line / 100) - (1 - result["Confidence"]),
        result["Confidence"] * (100 / line.abs()) - (1 - result["Confidence"]),
    )
    result.loc[line.isna(), "Expected Value"] = np.nan
    return result


@st.cache_data(ttl=3600, show_spinner=False)
def download_advantage_boxes(year):
    url = f"https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_team_box/team_box_{int(year)}.csv"
    with urlopen(url, timeout=20) as response:
        return pd.read_csv(BytesIO(response.read()), low_memory=False)


def team_data_details(team_id, published, derived, week):
    """Return the source label and eligible pregame metrics for a native expander."""
    if team_id is None:
        return "Data unavailable", "No matching team identifier was found.", {}
    tid = int(team_id)
    if tid in derived:
        info = derived[tid]
        return "Estimated from scores", (
            f"Provisional metrics from {info['games']} completed FBS game(s), "
            f"through Week {info['through_week']}. Prior profiles are adjusted using scores; "
            "these are not published advanced statistics."
        ), {}
    rows = published[(published["team_id"] == tid) & (published["through_week"] < week)]
    if rows.empty:
        return "Prior data only", (
            "No eligible current-season advanced snapshot or scoring fallback is available. "
            "FCS games are excluded from the scoring fallback; advanced summaries may also be missing."
        ), {}
    latest = rows.sort_values("through_week").iloc[-1]
    metrics = {}
    for column, label, percent in [
        ("adj_off_epa", "Adjusted offensive EPA", False),
        ("adj_def_epa", "Adjusted defensive EPA", False),
        ("success_off", "Offensive success rate", True),
        ("success_def", "Defensive success rate", True),
        ("explosive_off", "Offensive explosive-play rate", True),
        ("explosive_def", "Defensive explosive-play rate", True),
    ]:
        value = pd.to_numeric(latest.get(column), errors="coerce")
        metrics[label] = ("Unavailable" if pd.isna(value) else
                          f"{value:.1%}" if percent else f"{value:.3f}")
    return "Advanced stats", (
        f"Published snapshot through Week {int(latest['through_week'])}, "
        f"used for the Week {week} prediction. Source: SportsDataverse."
    ), metrics




# Free, daily-cached red-zone game logs. Kept separate from model inputs.
class RedZoneHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.links = [], []
        self.row = self.cell = self.link = None
    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        if tag in ("td", "th") and self.row is not None:
            self.cell = ""
        if tag == "a":
            self.link = [dict(attrs).get("href", ""), ""]
    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data
        if self.link is not None:
            self.link[1] += data
    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join(self.cell.split()))
            self.cell = None
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        if tag == "a" and self.link is not None:
            self.links.append(self.link)
            self.link = None


def red_zone_name(name):
    name = re.sub(r"[^a-z0-9]", "", str(name).lower())
    aliases = {"connecticut": "uconn", "massachusetts": "umass",
               "miamiohio": "miamioh", "miamifl": "miami",
               "louisianalafayette": "louisiana", "middletennesseestate": "middletennessee",
               "sanjosestate": "sanjosestate", "southernmississippi": "southernmiss",
               "floridainternational": "fiu", "centralflorida": "ucf",
               "southflorida": "usf", "texaselpaso": "utep",
               "texassanantonio": "utsa", "hawaii": "hawaii"}
    return aliases.get(name, name)


def fetch_red_zone_html(url):
    with urlopen(url, timeout=12) as response:
        html = response.read().decode("utf-8", errors="replace")
    parser = RedZoneHTMLParser()
    parser.feed(html)
    return html, parser


@st.cache_data(ttl=86400, show_spinner=False)
def red_zone_team_index(year):
    _, parser = fetch_red_zone_html(
        f"https://cfbstats.com/{int(year)}/leader/national/team/offense/split01/category27/sort01.html")
    index = {}
    for href, name in parser.links:
        match = re.fullmatch(r"/" + str(int(year)) + r"/team/(\d+)/redzone/offense/split.html", href)
        if match:
            key = red_zone_name(name)
            if key in index and index[key] != match.group(1):
                raise ValueError("Ambiguous red-zone team name")
            index[key] = match.group(1)
    if len(index) < 100:
        raise ValueError("Incomplete red-zone team index")
    return index


def parse_red_zone_log(html, year):
    parser = RedZoneHTMLParser()
    parser.feed(html)
    through = re.search(r"through\s+(\d{2}/\d{2}/\d{4})", html)
    if not through:
        raise ValueError("Missing red-zone update date")
    updated = datetime.strptime(through.group(1), "%m/%d/%Y").date()
    records = {}
    for row in parser.rows:
        if not row or not re.fullmatch(r"\d{2}/\d{2}/\d{2}", row[0]):
            continue
        if len(row) != 11:
            raise ValueError("Unexpected red-zone game row")
        date = datetime.strptime(row[0], "%m/%d/%y").date()
        if date.year not in (int(year), int(year)+1):
            raise ValueError("Wrong red-zone season")
        attempts, scores, td, fg = [int(row[i]) for i in (4, 5, 7, 9)]
        if min(attempts, scores, td, fg) < 0 or scores != td+fg or scores > attempts:
            raise ValueError("Invalid red-zone counts")
        opponent = red_zone_name(row[1].lstrip("@+ "))
        key = (date.isoformat(), opponent)
        if key in records:
            raise ValueError("Duplicate red-zone game")
        records[key] = (attempts, td)
    return {"records": records, "through": updated.isoformat()}


@st.cache_data(ttl=86400, show_spinner=False)
def red_zone_logs(year, source_id):
    result = {}
    for unit in ("offense", "defense"):
        url = f"https://cfbstats.com/{int(year)}/team/{int(source_id)}/redzone/{unit}/gamelog.html"
        html, _ = fetch_red_zone_html(url)
        result[unit] = parse_red_zone_log(html, year)
    result["checked"] = datetime.now(ZoneInfo("America/Chicago")).strftime("%b %d, %I:%M %p %Z")
    result["source_id"] = str(source_id)
    return result


def red_zone_totals(logs, schedule, tid, week, year, kickoff):
    required = {"season", "week", "home_id", "away_id", "home_team", "away_team",
                "home_division", "away_division", "completed", "start_date"}
    if not required.issubset(schedule.columns) or pd.isna(kickoff):
        return None
    past = schedule[pd.to_numeric(schedule["season"], errors="coerce").eq(int(year))
                    & pd.to_numeric(schedule["week"], errors="coerce").lt(int(week))]
    past = past[past["completed"].astype(str).str.lower().isin(["true", "1", "1.0", "t", "yes"])]
    past = past[past["home_division"].astype(str).str.lower().eq("fbs")
                & past["away_division"].astype(str).str.lower().eq("fbs")]
    past = past[(pd.to_numeric(past.home_id, errors="coerce") == int(tid))
                | (pd.to_numeric(past.away_id, errors="coerce") == int(tid))]
    totals = {"offense": [0, 0], "defense": [0, 0]}
    seen = set()
    for _, game in past.iterrows():
        start = pd.to_datetime(game.start_date, utc=True, errors="coerce")
        if pd.isna(start) or start >= kickoff:
            return None
        opponent = game.away_team if int(game.home_id) == int(tid) else game.home_team
        key = (start.tz_convert("America/Chicago").date().isoformat(), red_zone_name(opponent))
        if key in seen:
            return None
        seen.add(key)
        for unit in totals:
            record = logs[unit]["records"].get(key)
            if record is None:
                return None
            totals[unit][0] += record[0]
            totals[unit][1] += record[1]
    return totals


def red_zone_matchup_html(pick, game, schedule, year, week, index):
    if float(pick["Confidence"]) >= .80 or len(game) != 1:
        return ""
    g = game.iloc[0]
    kickoff = pd.to_datetime(g.get("start_date"), utc=True, errors="coerce")
    totals, sources = {}, {}
    try:
        for side in ("home", "away"):
            source_id = index.get(red_zone_name(g[side+"_team"]))
            if source_id is None:
                return ""
            sources[side] = red_zone_logs(year, source_id)
            totals[side] = red_zone_totals(sources[side], schedule, g[side+"_id"], week, year, kickoff)
            if totals[side] is None:
                return ""
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        return ""
    lines = []
    for attack, defend in (("home", "away"), ("away", "home")):
        attempts, td = totals[attack]["offense"]
        allowed_attempts, allowed_td = totals[defend]["defense"]
        if min(attempts, allowed_attempts) < 10:
            continue
        # Display the comparison without treating a difference between unlike
        # offensive/defensive rates as a calibrated matchup advantage.
        lines.append(f"{g[attack+'_team']} scored TDs on {td}/{attempts} red-zone trips ({td/attempts:.0%}); "
                     f"{g[defend+'_team']} allowed TDs on {allowed_td}/{allowed_attempts} opponent trips ({allowed_td/allowed_attempts:.0%}).")
    if not lines:
        return ""
    body = '<div class="pick-label">Red-zone touchdown comparison</div>' + "".join("<p>"+escape(line)+"</p>" for line in lines)
    body += '<p class="venue-label">Completed FBS games before this week only. At least 10 trips per compared unit; this display threshold is not a validated betting signal. Trip conversion differs from successful-play rate and does not change the model.</p>'
    for side in ("home", "away"):
        data = sources[side]
        through = min(data["offense"]["through"], data["defense"]["through"])
        url = f"https://cfbstats.com/{int(year)}/team/{int(data['source_id'])}/redzone/offense/gamelog.html"
        body += f'<p class="venue-label"><a href="{url}" target="_blank" rel="noopener noreferrer">{escape(str(g[side+"_team"]))} · CFBStats</a>: source through {escape(through)}; checked {escape(data["checked"])}. Later games are excluded.</p>'
    return body


def matchup_insights_html(pick, game, published, schedule, week, derived_ids):
    """Descriptive pregame comparisons only; never alter model probabilities."""
    if float(pick["Confidence"]) >= .80 or len(game) != 1:
        return ""
    def number(value):
        try:
            value = float(value)
            return value if math.isfinite(value) else None
        except (ValueError, TypeError):
            return None
    def panel(body):
        return '<details class="card-details"><summary>Matchup insights</summary>' + body + '<p class="venue-label">Descriptive comparisons of published pregame rates, not additional model inputs or predicted matchup rates. Opponent quality and small samples can affect these numbers.</p></details>'
    needed = {"team_id", "through_week", "valid_games", "plays_off", "plays_def"}
    if not needed.issubset(published.columns):
        return panel("<p>Insufficient verified sample information for matchup comparisons.</p>")
    g = game.iloc[0]
    ids = [int(g["home_id"]), int(g["away_id"])]
    if any(tid in derived_ids for tid in ids):
        return panel("<p>Matchup comparisons are withheld because a team uses provisional metrics.</p>")
    # Use only the immediately preceding week's published snapshot.
    pool = published[pd.to_numeric(published["through_week"], errors="coerce").eq(int(week)-1)].copy()
    fbs_ids = set()
    if {"home_division", "away_division"}.issubset(schedule.columns):
        for side in ("home", "away"):
            rows = schedule[schedule[side+"_division"].astype(str).str.lower().eq("fbs")]
            fbs_ids.update(pd.to_numeric(rows[side+"_id"], errors="coerce").dropna().astype(int))
    if not fbs_ids:
        return panel("<p>FBS reference data is unavailable for matchup comparisons.</p>")
    pool = pool[pd.to_numeric(pool["team_id"], errors="coerce").isin(fbs_ids)]
    pool = pool[pd.to_numeric(pool["valid_games"], errors="coerce").ge(2)
                & pd.to_numeric(pool["plays_off"], errors="coerce").ge(100)
                & pd.to_numeric(pool["plays_def"], errors="coerce").ge(100)]
    selected = {}
    for tid in ids:
        rows = pool[pd.to_numeric(pool["team_id"], errors="coerce").eq(tid)]
        if len(rows) != 1:
            return panel("<p>Not enough recent published data: each team needs at least two verified games and 100 recorded plays on each side of the ball through the previous week.</p>")
        selected[tid] = rows.iloc[0]
    candidates = []
    metrics = [("success", "Successful plays", .03),
               ("explosive", "Explosive plays", .015),
               ("red_zone_success", "Red-zone successful plays", .05)]
    for attacking, defending in (("home", "away"), ("away", "home")):
        offense = selected[int(g[attacking+"_id"])]
        defense = selected[int(g[defending+"_id"])]
        for metric, label, gap in metrics:
            off_col, def_col = metric+"_off", metric+"_def"
            if off_col not in pool or def_col not in pool:
                continue
            # Red-zone denominators are not in the current feed: omit the
            # comparison rather than infer reliability from total play counts.
            if metric == "red_zone_success":
                continue
            ov, dv = number(offense.get(off_col)), number(defense.get(def_col))
            if ov is None or dv is None or not (0 <= ov <= 1 and 0 <= dv <= 1):
                continue
            refs = []
            for col in (off_col, def_col):
                values = pd.to_numeric(pool[col], errors="coerce")
                values = values[values.between(0, 1)]
                if len(values) < 30:
                    break
                refs.append(float(values.median()))
            if len(refs) != 2:
                continue
            om, dm = refs
            if ov >= om+gap and dv >= dm+gap:
                interpretation = "Potential offensive opportunity"
                strength = min((ov-om)/gap, (dv-dm)/gap)
            elif ov <= om-gap and dv <= dm-gap:
                interpretation = "Potential defensive constraint"
                strength = min((om-ov)/gap, (dm-dv)/gap)
            else:
                continue
            attack_name, defend_name = str(g[attacking+"_team"]), str(g[defending+"_team"])
            text = (f"{interpretation}: {attack_name} vs. {defend_name}. "
                    f"{label}: {attack_name} offense {ov:.1%}; {defend_name} defense allows {dv:.1%}. "
                    f"Eligible FBS medians: {om:.1%} on offense and {dm:.1%} allowed.")
            candidates.append((strength, text))
    candidates.sort(key=lambda item: item[0], reverse=True)
    if candidates:
        body = "".join("<p>"+escape(text)+"</p>" for _, text in candidates[:2])
    else:
        body = "<p>No clear success-rate or explosive-play matchup stands out under these screening rules.</p>"
    body += (f'<p class="venue-label">Published through Week {int(week)-1}. '
             'At least 2 verified games and 100 plays per unit; comparisons require 30 eligible FBS teams. '
             'Screens use gaps of 3 percentage points for success rate and 1.5 for explosive plays on both sides of the matchup. '
             'These are descriptive thresholds, not backtested betting signals. Red-zone trip comparisons appear separately below when verified opportunity counts are available.</p>')
    return panel(body)


def matchup_strengths_html(record, side, winner, opponent):
    """Highlight verified pregame strengths, separate from model contributions."""
    if record.get("status") != "ok":
        return ""
    other_side = "away" if side == "home" else "home"
    own, other = record.get(side, []), record.get(other_side, [])
    if len(own) < 5 or len(other) < 5:
        return ""
    points = []
    for index in (2, 3, 4):
        try:
            a, b = float(own[index]), float(other[index])
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(a) and math.isfinite(b)):
            continue
        # Compare at the displayed precision so a rounded tie is not an edge.
        precision = 2 if index in (2, 4) else 3
        if index in (2, 3) and round(a, precision) >= round(b, precision):
            continue
        if index == 4 and round(a, precision) <= round(b, precision):
            continue
        if index == 2:
            label = "Stopping the run"
            detail = f"{winner} has allowed {a:.2f} yards per carry, compared with {b:.2f} for {opponent}."
        elif index == 3:
            label = "Limiting completions"
            detail = f"Opponents have completed {a:.1%} of passes against {winner}, compared with {b:.1%} against {opponent}."
        else:
            label = "Turnover battle"
            detail = f"{winner} has a {a:+.2f} turnover margin per game versus {b:+.2f} for {opponent} (takeaways minus giveaways)."
        points.append(f'<p><strong>{label}:</strong> {escape(detail)}</p>')
    if not points:
        return ""
    return (
        '<div class="matchup-strengths">' + "".join(points[:2])
        + '<p class="venue-label">Based on earlier FBS games this season; opponents faced may differ.</p></div>'
    )


def betting_odds_html(row):
    """Use team names and a single empty-state label for missing moneylines."""
    away = escape(str(row["Away Team"]))
    home = escape(str(row["Home Team"]))
    away_ml = format_moneyline(row.get("Away ML"))
    home_ml = format_moneyline(row.get("Home ML"))
    if away_ml == "Unavailable" and home_ml == "Unavailable":
        moneyline = '<div class="pick-label">Moneyline · Unavailable</div>'
    else:
        moneyline = (
            f'<div class="pick-label">Moneyline · {escape(str(row["ML Source"]))}</div>'
            f'<div class="odds-prices"><span>{away} <strong>{away_ml}</strong></span>'
            f'<span>{home} <strong>{home_ml}</strong></span></div>'
        )
    return (
        '<div class="odds-box">' + moneyline
        + f'<div class="pick-label" style="margin-top:10px">Spread · {escape(str(row["Spread Source"]))}</div>'
        + f'<div class="odds-prices"><span>{away} <strong>{escape(str(row["Away Spread"]))}</strong></span>'
        + f'<span>{home} <strong>{escape(str(row["Home Spread"]))}</strong></span></div>'
        + f'<div class="venue-label" style="margin-top:8px">{escape(str(row["Odds Type"]))}</div></div>'
    )


def weather_condition_icon(condition):
    """Match the provider's condition labels; unknown conditions stay neutral."""
    icons = {
        "Clear": "☀️", "Mainly clear": "🌤️", "Partly cloudy": "⛅",
        "Overcast": "☁️", "Fog": "🌫️", "Drizzle": "🌦️",
        "Freezing drizzle": "🧊", "Rain": "🌧️", "Freezing rain": "🧊",
        "Snow": "🌨️", "Rain showers": "🌧️", "Snow showers": "🌨️",
        "Thunderstorms": "⛈️",
    }
    return icons.get(condition, "🌡️")


def weather_card_html(weather):
    """Compact game-window forecast panel for matchup cards."""
    weather = weather or {}
    status = str(weather.get("status") or "missing")
    if status == "indoor":
        venue = str(weather.get("venue_name") or "Indoor venue")
        return (
            '<div class="result-box" style="margin-top:10px">'
            '<div class="pick-label">Game weather</div>'
            f'<strong><span aria-hidden="true">🏟️</span> {escape(venue)}</strong><div>Indoor venue · outdoor weather is not expected to affect play.</div></div>'
        )
    if status != "ok":
        reason = str(weather.get("reason") or "Forecast unavailable.")
        return (
            '<div class="result-box" style="margin-top:10px">'
            '<div class="pick-label">Game weather</div>'
            f'<div><span aria-hidden="true">❔</span> {escape(reason)}</div></div>'
        )

    def finite(value):
        try:
            value = float(value)
            return value if math.isfinite(value) else None
        except (TypeError, ValueError):
            return None

    condition = str(weather.get("condition") or weather.get("weather_type") or "Forecast")
    temp = finite(weather.get("temperature_f"))
    feels = finite(weather.get("feels_like_f"))
    precip = finite(weather.get("precip_mm"))
    snow = finite(weather.get("snowfall"))
    wind = finite(weather.get("max_wind_mph"))
    gust = finite(weather.get("max_gust_mph"))
    source = str(weather.get("source_type") or "Forecast")
    location = str(weather.get("location") or "").strip()
    details = []
    if temp is not None:
        temp_text = f"{temp:.0f}°F"
        if feels is not None and abs(feels-temp) >= 3:
            temp_text += f" · feels {feels:.0f}°F"
        details.append(temp_text)
    if precip is not None:
        details.append(f"Precip {precip:.1f} mm")
    if snow is not None and snow > 0:
        details.append(f"Snow {snow:.1f}")
    if wind is not None:
        details.append(f"Wind up to {wind:.0f} mph")
    if gust is not None:
        details.append(f"Gusts {gust:.0f} mph")
    headline = "⚠ Inclement-weather threshold met" if weather.get("inclement") is True else source
    border = "#e9a23b" if weather.get("inclement") is True else "#58ae87"
    loc = f" · {escape(location)}" if location else ""
    icon = weather_condition_icon(condition)
    windy = (wind is not None and wind >= 20) or (gust is not None and gust >= 30)
    wind_badge = (
        ' <span style="white-space:nowrap"><span aria-hidden="true">💨</span> Windy</span>'
        if windy else ""
    )
    return (
        f'<div class="result-box" style="margin-top:10px;border-left:4px solid {border}">'
        f'<div class="pick-label">{escape(headline)}</div>'
        f'<strong><span aria-hidden="true" style="font-size:1.5em;vertical-align:middle">{icon}</span> {escape(condition)}</strong>{wind_badge}{loc}'
        f'<div>{" · ".join(escape(x) for x in details)}</div>'
        '</div>'
    )


def team_logo_url(team_id):
    """ESPN's public college-football logo endpoint, keyed by team ID."""
    try:
        return f"https://a.espncdn.com/i/teamlogos/ncaa/500/{int(team_id)}.png"
    except (TypeError, ValueError, OverflowError):
        return ""



@st.cache_data(ttl=3600, show_spinner=False)
def embedded_team_logos(urls):
    """Serve cached logo bytes with the cards instead of relying on phone CDN access."""
    def download(url):
        try:
            with urlopen(url, timeout=4) as response:
                data = response.read(500_001)
            if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) <= 500_000:
                return url, "data:image/png;base64," + base64.b64encode(data).decode("ascii")
        except (OSError, ValueError):
            pass
        # Keep the original image URL if this server cannot retrieve the logo.
        return url, url

    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(pool.map(download, urls))


def payout_outcomes(stake, line):
    """American moneyline payout rounded to cents, including returned stake."""
    formatted = format_moneyline(line)
    if formatted == "Unavailable":
        return None
    amount = Decimal(str(stake)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if not amount.is_finite() or amount < 0:
        raise ValueError("Stake must be a nonnegative amount.")
    odds = Decimal(formatted)
    profit = (amount * (odds / 100 if odds > 0 else 100 / abs(odds))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {"Stake": float(amount), "Return if win": float(amount + profit),
            "Profit if win": float(profit), "Loss if lose": float(-amount)}


def future_priced_picks(predictions, game_schedule, now_utc):
    """Require a future kickoff and a published selected-side moneyline."""
    result = predictions.copy()
    starts = {(r["home_team"], r["away_team"]): pd.to_datetime(r.get("start_date"), utc=True, errors="coerce")
              for _, r in game_schedule.iterrows()}
    mask = []
    for _, row in result.iterrows():
        date = starts.get((row["Home Team"], row["Away Team"]))
        mask.append(pd.notna(date) and date > now_utc and row["Status"] == "Awaiting final"
                    and format_moneyline(row["Bet Line"]) != "Unavailable")
    return result.loc[pd.Series(mask, index=result.index, dtype=bool)]


def christians_parlay(predictions, game_schedule, now_utc, stake=10.0):
    """Build Christian's featured four-leg Value Pick parlay for the selected week.

    Primary: 2 Tier 4 + 1 Tier 1 + 1 Tier 2/3/5.
    Fallback: 2 Tier 4 + 2 Tier 1.
    Only future, distinct games with DraftKings prices are eligible.
    """
    if predictions is None or predictions.empty or "Value Selected" not in predictions:
        return None

    pool = predictions[
        predictions["Value Selected"].fillna(False).astype(bool)
        & pd.to_numeric(predictions.get("Week"), errors="coerce").ge(3)
    ].copy()
    if pool.empty:
        return None

    starts = {}
    if "game_id" in game_schedule:
        for _, game in game_schedule.iterrows():
            try:
                gid = int(game["game_id"])
            except (TypeError, ValueError, OverflowError):
                continue
            starts[gid] = pd.to_datetime(game.get("start_date"), errors="coerce", utc=True)

    keep = []
    prices = []
    decimals = []
    for _, row in pool.iterrows():
        try:
            gid = int(row["Game ID"])
        except (KeyError, TypeError, ValueError, OverflowError):
            keep.append(False); prices.append("Unavailable"); decimals.append(np.nan)
            continue
        kickoff = starts.get(gid)
        price = format_moneyline(row.get("Value Price"))
        source = str(row.get("Value Source", "")).lower().replace(" ", "")
        eligible = (
            pd.notna(kickoff)
            and kickoff > now_utc
            and str(row.get("Status", "")) not in {"Final", "In progress"}
            and price != "Unavailable"
            and "draftkings" in source
        )
        keep.append(bool(eligible))
        prices.append(price)
        if eligible:
            payout = payout_outcomes(100, price)
            decimals.append(payout["Return if win"] / 100 if payout else np.nan)
        else:
            decimals.append(np.nan)

    pool["_eligible"] = keep
    pool["_price"] = prices
    pool["_decimal"] = decimals
    pool = pool[pool["_eligible"]].copy()
    if pool.empty:
        return None

    pool["_stage"] = pd.to_numeric(pool["Value Stage"], errors="coerce")
    pool["_rank"] = pd.to_numeric(pool.get("Value Rank"), errors="coerce").fillna(9999)

    # Tier 4 is highly reliable but low-return, so use the two eligible prices
    # with the best payout (closest to the -505 edge of the validated band).
    tier4 = pool[pool["_stage"].eq(4)].sort_values(
        ["_decimal", "_rank"], ascending=[False, True], kind="stable"
    )
    # Tier 1 already has its own preferred waterfall ordering/bands.
    tier1 = pool[pool["_stage"].eq(1)].sort_values(
        ["_rank", "_decimal"], ascending=[True, False], kind="stable"
    )
    # For the fourth leg, use the highest available payout from another tier.
    other = pool[pool["_stage"].isin([2, 3, 5])].sort_values(
        ["_decimal", "_rank"], ascending=[False, True], kind="stable"
    )

    selected = None
    formula = None
    if len(tier4) >= 2 and len(tier1) >= 1 and len(other) >= 1:
        selected = pd.concat([tier4.head(2), tier1.head(1), other.head(1)])
        formula = "2 Tier 4 + 1 Tier 1 + 1 other tier"
    elif len(tier4) >= 2 and len(tier1) >= 2:
        selected = pd.concat([tier4.head(2), tier1.head(2)])
        formula = "Fallback · 2 Tier 4 + 2 Tier 1"

    if selected is None or len(selected) != 4:
        return None
    if selected["Game ID"].nunique() != 4:
        return None

    multiplier = float(np.prod(pd.to_numeric(selected["_decimal"], errors="coerce")))
    if not np.isfinite(multiplier):
        return None
    amount = Decimal(str(stake)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    returned = (amount * Decimal(str(multiplier))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    legs = []
    for _, row in selected.iterrows():
        stage = int(row["_stage"])
        market = str(row.get("Value Market", ""))
        line = str(row.get("Value Line", ""))
        pick = str(row.get("Value Pick", ""))
        bet = f"{pick} {line}" if market == "Spread" else f"{pick} ML {line}"
        legs.append({
            "game_id": int(row["Game ID"]),
            "tier": str(row.get("Value Tier", "")),
            "stage": stage,
            "pick": pick,
            "bet": bet,
            "price": str(row["_price"]),
            "away": str(row.get("Away Team", "")),
            "home": str(row.get("Home Team", "")),
        })

    return {
        "formula": formula,
        "legs": legs,
        "stake": float(amount),
        "return": float(returned),
        "profit": float(returned - amount),
        "loss": -float(amount),
        "sportsbook": "DraftKings",
    }


def rank_parlays(pool, legs, stake, goal, limit=5):
    """Exact top combinations within a bounded pool; one sportsbook, distinct teams."""
    def candidates():
        for combo in combinations(pool.to_dict("records"), legs):
            if len({r["ML Source"] for r in combo}) != 1:
                continue
            teams = [r[t] for r in combo for t in ("Home Team", "Away Team")]
            if len(set(teams)) != 2 * legs:
                continue
            probability = math.prod(float(r["Confidence"]) for r in combo)
            multiplier = Decimal("1")
            for r in combo:
                odds = Decimal(format_moneyline(r["Bet Line"]))
                multiplier *= 1 + (odds / 100 if odds > 0 else 100 / abs(odds))
            amount = Decimal(str(stake)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            returned = (amount * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            ev = probability * float(multiplier) - 1
            score = probability if goal == "Highest win probability" else float(multiplier) if goal == "Highest payout" else ev
            yield {"legs": combo, "probability": probability, "return": float(returned),
                   "profit": float(returned - amount), "loss": -float(amount),
                   "ev": ev, "score": score}
    return nlargest(limit, candidates(), key=lambda x: x["score"])


def simulate_stakes(predictions, stakes):
    rows = []
    for _, pick in predictions.iterrows():
        confidence = float(pick["Confidence"])
        tier = "High" if confidence >= .8 else "Moderate" if confidence >= .7 else "Lean" if confidence >= .6 else "Toss-up"
        stake = Decimal(str(stakes[tier])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if "Bet Line" in pick and pd.notna(pick["Bet Line"]):
            line = pick["Bet Line"]
        else:
            line = pick["Home ML"] if pick["Predicted Side"] == "Home" else pick["Away ML"]
        valid_line = format_moneyline(line)
        reason = "Settled"
        returned = profit = None
        if stake <= 0:
            reason = "No bet · zero stake"
        elif valid_line == "Unavailable":
            reason = "Excluded · missing bet price"
        elif pick["Status"] != "Final":
            reason = "Pending final result"
        else:
            odds = Decimal(valid_line)
            grade = str(pick.get("Pick Result", ""))
            if grade in ("Push", "Not graded") or pick.get("Actual Winner") == "Tie":
                returned, profit = stake, Decimal("0")
            elif grade == "Correct":
                profit = (stake * (odds / 100 if odds > 0 else 100 / abs(odds))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                returned = stake + profit
            elif grade == "Incorrect":
                returned, profit = Decimal("0"), -stake
            elif pick["Predicted Winner"] == pick["Actual Winner"]:
                profit = (stake * (odds / 100 if odds > 0 else 100 / abs(odds))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                returned = stake + profit
            else:
                returned, profit = Decimal("0"), -stake
        potential = payout_outcomes(stake, valid_line) if stake > 0 else None
        rows.append({
            "Return if pick wins": potential["Return if win"] if potential else None,
            "Profit if pick wins": potential["Profit if win"] if potential else None,
            "Loss if pick loses": potential["Loss if lose"] if potential else None,
            "Week": int(pick["Week"]), "Away Team": pick["Away Team"], "Home Team": pick["Home Team"],
            "Pick": pick["Predicted Winner"], "Bet": pick.get("Bet Display", pick["Predicted Winner"]),
            "Market": pick.get("Bet Market", "Moneyline"), "Tier": tier, "Confidence": confidence,
            "Odds": valid_line, "Moneyline": valid_line, "Sportsbook": pick["ML Source"], "Actual Winner": pick["Actual Winner"],
            "Planned Stake": float(stake), "Stake": float(stake) if reason == "Settled" else 0.0,
            "Returned": float(returned) if returned is not None else None,
            "Net Profit": float(profit) if profit is not None else None, "Scenario Status": reason,
            "Won": reason == "Settled" and pick["Pick Result"] == "Correct",
            "Lost": reason == "Settled" and pick["Pick Result"] == "Incorrect",
        })
    return pd.DataFrame(rows)


def summarize_scenario(detail, group):
    rows = []
    for key, frame in detail.groupby(group, sort=True):
        settled = frame[frame["Scenario Status"] == "Settled"]
        risked = round(settled["Stake"].sum(), 2)
        net = round(settled["Net Profit"].sum(), 2)
        rows.append({group: key, "Bets": len(settled), "Won": int(settled["Won"].sum()),
                     "Lost": int(settled["Lost"].sum()), "Staked": risked,
                     "Returned": round(settled["Returned"].sum(), 2), "Net Profit": net,
                     "ROI": net / risked if risked else None,
                     "Excluded / pending": int((frame["Scenario Status"] != "Settled").sum())})
    return pd.DataFrame(rows)


@st.fragment(run_every="30s")
def watch_results(season, original, date_range, original_odds, event_ids=(), original_live=None):
    if date_range:
        try:
            snapshot = download_live_scores(date_range, event_ids)
            if snapshot["games"] != (original_live or {}):
                st.rerun()
            st.caption("Live scoreboard last checked: " + snapshot["retrieved"])
        except Exception:
            st.warning("Live score refresh failed. Displayed scores may be stale; the next check will retry.")
    if original is not None:
        try:
            if not download_schedule(season).equals(original):
                st.rerun()
        except Exception:
            st.caption("Results refresh is temporarily unavailable. Showing the last loaded data.")
    if date_range:
        try:
            if download_market_odds(date_range, event_ids)["quotes"] != original_odds:
                st.rerun()
        except Exception:
            st.caption("Odds refresh is temporarily unavailable. Previously displayed lines may be stale.")
    st.caption("Live scores refresh about every minute while this page is open; odds and schedule results refresh every 5 minutes. Provider updates may be delayed.")

st.markdown("""
<style>
.block-container {max-width:1280px;padding-top:4rem;padding-bottom:3rem;}
.hero {background:linear-gradient(115deg,#102c26,#163e35 65%,#265b46);color:#fff;border-radius:24px;padding:32px 36px;margin-bottom:24px;position:relative;overflow:hidden;}
.hero:after {content:"";position:absolute;width:260px;height:260px;border:1px solid #ffffff18;border-radius:50%;right:-60px;top:-100px;box-shadow:0 0 0 45px #ffffff06,0 0 0 90px #ffffff04;pointer-events:none;}
.eyebrow {font-size:12px;letter-spacing:2px;font-weight:700;color:#bde7ca;text-transform:uppercase;}
.hero h1 {font-size:clamp(30px,5vw,46px);letter-spacing:-1.5px;margin:8px 0;color:white;line-height:1.12;}
.hero p {color:#d9e9df;margin:10px 0 0;font-size:16px;}
.overview {display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:14px 0 24px;}
.stat {border:1px solid #80978b40;border-radius:16px;padding:18px 20px;background:var(--secondary-background-color);}
.stat strong {display:block;font-size:28px;line-height:1.4;letter-spacing:-1px;}
.stat span {font-size:13px;opacity:.75;}
.pick-grid {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin:14px 0 24px;}
.pick-card {border:1px solid #80978b55;border-radius:18px;padding:22px;background:var(--secondary-background-color);min-width:0;}
.card-top {display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:20px;font-size:12px;}
.badge {background:#dff1e5;color:#185431;border-radius:20px;padding:5px 9px;font-size:11px;font-weight:700;white-space:nowrap;}
.badge.incorrect {background:#fbe1df;color:#8b2925;}
.result-box {margin-top:16px;padding-top:14px;border-top:1px solid #80978b40;font-size:13px;}
.result-score {font-size:13px;margin:8px 0;overflow-wrap:anywhere;}
.badge.close {background:#fff0d1;color:#704900;}
.team-line {display:flex;justify-content:space-between;align-items:center;gap:12px;margin:12px 0;font-size:15px;}
.team-name {overflow-wrap:anywhere;}
.team-identity {display:flex;align-items:center;gap:9px;overflow-wrap:anywhere;}
.team-logo {width:30px;height:30px;object-fit:contain;flex:0 0 30px;}
.team-line strong {white-space:nowrap;}
.venue-label {font-size:10px;opacity:.6;text-transform:uppercase;letter-spacing:1px;display:block;}
.pick-result {border-top:1px solid #80978b40;margin-top:18px;padding-top:16px;}
.pick-label {font-size:11px;opacity:.7;text-transform:uppercase;letter-spacing:1.3px;}
.pick-winner {font-weight:750;font-size:21px;margin:4px 0 12px;overflow-wrap:anywhere;}
.conf-row {display:flex;justify-content:space-between;font-size:12px;margin-bottom:7px;}
.conf-track {height:6px;background:#80978b30;border-radius:5px;overflow:hidden;}
.conf-fill {height:100%;background:#41a577;border-radius:5px;}
.odds-box {border:1px solid #80978b40;border-radius:12px;padding:12px;margin-top:16px;}
.odds-prices {display:flex;justify-content:space-between;gap:12px;font-size:14px;margin-top:8px;}
.odds-prices span {min-width:0;overflow-wrap:anywhere;}
.risk-note {font-size:12px;margin-top:14px;color:#986a17;}
.data-quality {font-size:11px;margin-top:5px;max-width:100%;}
.data-quality summary {cursor:pointer;display:list-item;list-style-position:inside;border-radius:8px;padding:4px 7px;width:fit-content;}
.data-quality.advanced summary {background:#dff1e5;color:#185431;}
.data-quality.estimated summary {background:#fff0d1;color:#704900;}
.data-quality.prior summary {background:#fbe1df;color:#8b2925;}
.data-quality span {display:block;padding:8px 0;line-height:1.5;}
.card-details {margin-top:12px;border-top:1px solid #80978b40;padding-top:12px;font-size:12px;}
.card-details summary {cursor:pointer;min-height:32px;}
.kickoff {font-size:12px;opacity:.75;margin-bottom:12px;}
.team-name {min-width:0;flex:1;}
.hero-brand {display:flex;align-items:center;gap:22px;position:relative;z-index:1;}
.hero-mark {font-size:58px;line-height:1;filter:drop-shadow(0 8px 10px #061b1540);}
@media (max-width:1000px) {.pick-grid {grid-template-columns:repeat(2,minmax(0,1fr));}}
@media (max-width:600px) {.block-container {padding:4rem 1rem 2rem;}.hero {padding:25px 22px;border-radius:18px;}.pick-grid {grid-template-columns:1fr;}.overview {gap:8px;}.stat {padding:12px 10px;}.stat strong {font-size:23px;}.stat span {font-size:11px;}}
@media (max-width:600px) {.hero-brand {gap:14px;}.hero-mark {font-size:42px;}}

/* Responsive dashboard skin; native theme colors preserve light/dark mode. */
.block-container {max-width:1320px;padding-top:3.5rem;padding-bottom:3rem;}
.hero {padding:24px 28px;margin-bottom:8px;border-radius:20px;background:linear-gradient(120deg,#102b29,#164f43);border:1px solid #82cbb32b;}
.hero h1 {font-size:clamp(26px,4vw,38px);letter-spacing:-1.1px;margin:5px 0;}
.hero p {font-size:14px;margin-top:6px;line-height:1.55;}
.hero-brand {gap:18px;}
.hero-mark {font-size:32px;background:#ffffff10;border:1px solid #ffffff25;border-radius:16px;padding:12px;}
.eyebrow {font-size:10px;letter-spacing:1.8px;color:#aee8d0;}
.overview {gap:10px;margin:8px 0 12px;}
.stat {padding:14px 18px;border-radius:14px;border-color:#80978b30;background:var(--secondary-background-color);}
.stat strong {font-size:26px;font-variant-numeric:tabular-nums;letter-spacing:-.7px;}
.stat span {font-size:12px;opacity:.8;}
[data-testid="stTabs"] [data-baseweb="tab-list"] {gap:6px;padding:6px 2px 10px;overflow-x:auto;scrollbar-width:thin;}
[data-testid="stTabs"] [data-baseweb="tab"] {height:42px;white-space:nowrap;border-radius:10px;padding:0 14px;border:1px solid #80978b30;}
[data-testid="stTabs"] [aria-selected="true"] {background:#164f43;color:#fff;border-color:#164f43;}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {background:#4bb48b;height:2px;}
[class*="st-key-matchup_card_"] {border-radius:18px;border:1px solid #80978b40;background:var(--secondary-background-color);padding:16px;}
[class*="st-key-matchup_card_"] [data-testid="stExpander"] {font-size:12px;}
[class*="st-key-gotw_card_"] {border-radius:18px;border:2px solid #b5ed73!important;background:var(--secondary-background-color);padding:16px;box-shadow:0 0 0 1px #b5ed7330,0 10px 28px #0000001f;}
[class*="st-key-gotw_card_"] [data-testid="stExpander"] {font-size:12px;}
.gotw-banner {margin:0 0 12px;padding:12px 14px;border:1px solid #b5ed7370;border-radius:12px;background:#b5ed7312;}
.gotw-kicker {font-size:10px;letter-spacing:1.5px;font-weight:800;color:#74b93d;text-transform:uppercase;margin-bottom:3px;}
.gotw-pick {font-size:16px;font-weight:800;line-height:1.35;}
.gotw-tiers {font-size:11px;opacity:.72;margin-top:3px;}
[class*="st-key-christians_parlay_"] {border:2px solid #b5ed73!important;border-radius:20px;background:linear-gradient(135deg,#b5ed7312,#164f430d);box-shadow:0 0 0 1px #b5ed7330,0 12px 32px #00000020;padding:18px;}
.christians-parlay-kicker {font-size:11px;letter-spacing:1.8px;font-weight:800;text-transform:uppercase;color:#74b93d;margin-bottom:4px;}
.christians-parlay-title {font-size:24px;font-weight:850;letter-spacing:-.6px;margin:0 0 4px;}
.christians-parlay-formula {font-size:12px;opacity:.75;margin-bottom:14px;}
.christians-parlay-leg {padding:9px 0;border-top:1px solid #80978b30;font-size:14px;line-height:1.45;}
.christians-parlay-leg:first-of-type {border-top:0;}
.christians-parlay-tier {font-size:10px;font-weight:800;letter-spacing:.8px;text-transform:uppercase;opacity:.68;}
.card-top {margin-bottom:8px;font-size:11px;letter-spacing:.3px;}
.kickoff {margin-bottom:10px;line-height:1.5;}
.team-line {margin:8px 0;gap:10px;font-size:15px;}
.team-line strong {font-size:17px;font-variant-numeric:tabular-nums;}
.team-logo {display:block;width:34px!important;height:34px!important;min-width:34px;max-width:34px;flex:0 0 34px;object-fit:contain;background:#f8fafc;border-radius:6px;padding:3px;box-sizing:border-box;}
.team-identity {font-weight:650;gap:8px;}
.venue-label {font-size:10px;opacity:.75;letter-spacing:.7px;}
.pick-result {padding:12px 14px;margin-top:10px;border:1px solid #4bb48b44;border-radius:12px;background:#4bb48b0c;}
.pick-winner {font-size:20px;margin:3px 0 8px;}
.pick-label {font-size:10px;letter-spacing:1px;opacity:.8;}
.conf-track {height:5px;}
.conf-fill {background:linear-gradient(90deg,#299c76,#6bcea4);}
.conf-row {font-size:12px;}
.odds-box {margin-top:10px;padding:10px 12px;border-radius:12px;}
.odds-prices {font-variant-numeric:tabular-nums;}
.result-box {margin-top:10px;padding-top:10px;line-height:1.5;}
.result-score {margin:6px 0;font-weight:600;}
.badge {font-size:10px;padding:5px 9px;letter-spacing:.2px;}
.card-details {margin-top:8px;padding-top:9px;line-height:1.6;}
.card-details summary {min-height:36px;display:list-item;list-style-position:inside;font-weight:600;padding:6px 0;}
.card-details summary:focus-visible {outline:2px solid #4bb48b;outline-offset:3px;border-radius:4px;}
[data-testid="stButton"] button {border-radius:10px;min-height:42px;}
[data-testid="stTextInput"] input {min-height:42px;}
@media (max-width:640px) {
 .block-container {padding:3.6rem .85rem 2rem;}
 .hero {padding:18px;border-radius:16px;}
 .hero-mark {font-size:25px;padding:9px;border-radius:12px;}
 .hero-brand {gap:12px;}
 .hero h1 {font-size:27px;letter-spacing:-.8px;}
 .hero p {font-size:13px;}
 .eyebrow {font-size:9px;letter-spacing:1.2px;}
 .overview {gap:6px;}
 .stat {padding:11px 9px;border-radius:12px;}
 .stat strong {font-size:23px;}
 .stat span {font-size:10px;line-height:1.4;display:block;}
 [data-testid="stTabs"] [data-baseweb="tab"] {font-size:13px;padding:0 11px;}
 [class*="st-key-matchup_card_"] {padding:13px;border-radius:15px;}
 .team-identity {font-size:14px;}
}

/* Matchday dashboard: redesigned hierarchy and distinct destination views. */
.hero {background:#102c29;padding:22px 26px;border-radius:18px;margin:0 0 6px;border-left:5px solid #b5ed73;}
.hero:after {width:340px;height:340px;right:-80px;top:-220px;border-color:#b5ed7335;}
.hero-mark {display:none;}
.hero h1 {font-size:clamp(30px,5vw,44px);font-weight:800;letter-spacing:-1.8px;}
.brand-dot {color:#b5ed73;}
.eyebrow {color:#b5ed73;font-size:10px;letter-spacing:2px;}
.hero p {color:#d5e5df;font-size:13px;margin-top:4px;}
.week-dashboard {margin:4px 0 14px;padding:20px 22px;background:var(--secondary-background-color);border:1px solid #80978b35;border-radius:18px;}
.week-heading {display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:18px;}
.section-kicker {font-size:10px;letter-spacing:1.8px;opacity:.75;font-weight:700;}
.week-heading h2 {font-size:26px;letter-spacing:-1px;margin:2px 0 0;padding:0;}
.week-state {font-size:11px;padding:7px 10px;border:1px solid #80978b50;border-radius:30px;white-space:nowrap;}
.dashboard-metrics {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;}
.dashboard-metrics>div {border-left:3px solid #58ae87;padding-left:12px;}
.dashboard-metrics strong {font-size:26px;font-variant-numeric:tabular-nums;letter-spacing:-.7px;display:block;}
.dashboard-metrics span {font-size:11px;opacity:.8;display:block;margin-top:3px;}
[data-testid="stTabs"] [data-baseweb="tab-list"] {background:var(--secondary-background-color);padding:8px;border-radius:14px;gap:5px;}
[data-testid="stTabs"] [data-baseweb="tab"] {border:0;font-weight:650;}
[class*="st-key-matchup_card_"] {border-top:3px solid #58ae87;}
.team-line {padding:10px 0;margin:0;border-bottom:1px solid #80978b25;}
.team-identity {font-size:17px;}
.pick-result {display:grid;grid-template-columns:1fr auto;gap:2px 12px;background:#58ae8710;border:0;border-left:3px solid #58ae87;border-radius:0 10px 10px 0;}
.pick-result .pick-label,.pick-result .conf-track {grid-column:1/-1;}
.pick-result .pick-winner {font-size:18px;margin:2px 0 6px;}
.pick-result .conf-row {align-items:center;gap:8px;margin:0;}
.pick-result .conf-row>span {display:none;}
.pick-result .conf-row strong {font-size:22px;}
@media(max-width:640px){
 .hero {padding:16px 18px;}
 .hero h1 {font-size:32px;}
 .week-dashboard {padding:16px;}
 .dashboard-metrics {grid-template-columns:repeat(2,minmax(0,1fr));gap:16px 10px;}
 .dashboard-metrics strong {font-size:25px;}
 .week-heading {margin-bottom:16px;}
 .team-identity {font-size:15px;}
 .pick-result .pick-winner {font-size:17px;}
}

/* Distinct section navigation; keep native tab labels and tour targets intact. */
.st-key-main_app_tabs [role="tablist"] {
 display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;
 width:100%;overflow:visible;border:0;padding:8px 0 18px;
}
.st-key-main_app_tabs [role="tab"] {
 display:flex;align-items:center;justify-content:flex-start;gap:12px;
 min-width:0;min-height:58px;height:auto;padding:14px 16px;margin:0;
 border:1px solid #80978b65;border-radius:12px;background:var(--secondary-background-color);
 color:var(--text-color);white-space:normal;box-sizing:border-box;
 transition:background .15s,border-color .15s;cursor:pointer;
}
.st-key-main_app_tabs [role="tab"] p {font-size:14px;font-weight:650;line-height:1.3;margin:0;}
.st-key-main_app_tabs [role="tab"]:hover {border-color:#58ae87;background:#58ae8720;}
.st-key-main_app_tabs [role="tab"][aria-selected="true"] {
 background:#164f43;color:#fff;border:2px solid #6ac59a;padding:13px 15px;
 box-shadow:0 2px 8px #00000015;
}
.st-key-main_app_tabs [role="tab"]:focus-visible {outline:3px solid #74bfa0;outline-offset:3px;}
.st-key-main_app_tabs .react-aria-SelectionIndicator {display:none;}
.st-key-main_app_tabs [role="tab"]::before {
 content:"";display:block;flex:0 0 22px;width:22px;height:22px;background:currentColor;
 mask:var(--nav-icon) center/contain no-repeat;-webkit-mask:var(--nav-icon) center/contain no-repeat;
}
@media(max-width:640px){
 .st-key-main_app_tabs [role="tablist"] {grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;padding-bottom:18px;}
 .st-key-main_app_tabs [role="tab"] {padding:13px 12px;gap:10px;min-height:56px;}
 .st-key-main_app_tabs [role="tab"][aria-selected="true"] {padding:12px 11px;}
 .st-key-main_app_tabs [role="tab"] p {font-size:13px;}
}
.st-key-main_app_tabs [role="tab"][data-key="1"] { --nav-icon:url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJibGFjayIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwYXRoIGQ9Ik0xMiAzIDIgMjFoMjBMMTIgM1oiLz48cGF0aCBkPSJNMTIgOXY1bTAgM3YxIi8+PC9zdmc+"); }
.st-key-main_app_tabs [role="tab"][data-key="0"] { --nav-icon:url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJibGFjayIgc3Ryb2tlLXdpZHRoPSIxLjgiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PHJlY3QgeD0iMyIgeT0iMyIgd2lkdGg9IjciIGhlaWdodD0iNyIgcng9IjIiLz48cmVjdCB4PSIxNCIgeT0iMyIgd2lkdGg9IjciIGhlaWdodD0iNyIgcng9IjIiLz48cmVjdCB4PSIzIiB5PSIxNCIgd2lkdGg9IjciIGhlaWdodD0iNyIgcng9IjIiLz48cmVjdCB4PSIxNCIgeT0iMTQiIHdpZHRoPSI3IiBoZWlnaHQ9IjciIHJ4PSIyIi8+PC9zdmc+"); }
.st-key-main_app_tabs [role="tab"][data-key="2"] { --nav-icon:url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJibGFjayIgc3Ryb2tlLXdpZHRoPSIxLjgiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PHBhdGggZD0ibTEyIDMgMi44IDUuNyA2LjIuOS00LjUgNC40IDEuMSA2LjItNS42LTMtNS42IDMgMS4xLTYuMkwzIDkuNmw2LjItLjlaIi8+PC9zdmc+"); }
.st-key-main_app_tabs [role="tab"][data-key="3"] { --nav-icon:url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJibGFjayIgc3Ryb2tlLXdpZHRoPSIxLjgiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PHBhdGggZD0iTTQgM3YxOGgxN005IDE2di01bTUgNVY3bTUgOVY0Ii8+PC9zdmc+"); }
.st-key-main_app_tabs [role="tab"][data-key="4"] { --nav-icon:url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJibGFjayIgc3Ryb2tlLXdpZHRoPSIxLjgiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PHJlY3QgeD0iNCIgeT0iMyIgd2lkdGg9IjE2IiBoZWlnaHQ9IjE4IiByeD0iMiIvPjxwYXRoIGQ9Ik04IDdoOE04IDEyaDJtNCAwaDJtLTggNWgybTQgMGgyIi8+PC9zdmc+"); }
.st-key-main_app_tabs [role="tab"][data-key="5"] { --nav-icon:url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJibGFjayIgc3Ryb2tlLXdpZHRoPSIxLjgiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PGNpcmNsZSBjeD0iNiIgY3k9IjUiIHI9IjIiLz48Y2lyY2xlIGN4PSIxOCIgY3k9IjUiIHI9IjIiLz48Y2lyY2xlIGN4PSIxMiIgY3k9IjE5IiByPSIyIi8+PHBhdGggZD0iTTYgN3Y0bDYgNiA2LTZWNyIvPjwvc3ZnPg=="); }
.st-key-main_app_tabs [role="tab"][data-key="6"] { --nav-icon:url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJibGFjayIgc3Ryb2tlLXdpZHRoPSIxLjgiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PHBhdGggZD0iTTYgM2gxMnYxOGwtMy0yLTMgMi0zLTItMyAyWk05IDdoNm0tNiA0aDZtLTYgNGgzIi8+PC9zdmc+"); }
.st-key-main_app_tabs [role="tab"][data-key="7"] { --nav-icon:url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJibGFjayIgc3Ryb2tlLXdpZHRoPSIxLjgiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PGNpcmNsZSBjeD0iMTIiIGN5PSIxMiIgcj0iOSIvPjxwYXRoIGQ9Ik0xMiAxMXY2bTAtMTB2MSIvPjwvc3ZnPg=="); }
</style>
<div class="hero"><div class="hero-brand"><div class="hero-mark">🏈</div><div><div class="eyebrow">COLLEGE FOOTBALL · MATCHDAY HQ</div>
<h1>Saturday Forecast<span class="brand-dot">.</span></h1><p>Your slate. Your picks. Your game plan.</p></div></div></div>
""", unsafe_allow_html=True)

show_app_tour()

now = datetime.now(timezone.utc)
year = now.year if now.month >= 7 else now.year - 1
tour_at("schedule")
season_col, week_col = st.columns([1, 2])
with season_col:
    season = int(st.number_input("Season", min_value=2001, max_value=now.year + 1, value=year))
with st.sidebar:
    st.header("Data settings")
    st.caption("Schedules and team statistics load automatically. No uploads needed.")
    if st.button("Refresh all data", use_container_width=True):
        download_live_scores.clear()
        download_live_event.clear()
        download_schedule.clear()
        download_summary.clear()
        download_advantage_boxes.clear()
        download_market_odds.clear()
        download_archived_event.clear()
        download_event_moneylines.clear()
    st.caption("Live scores refresh about every minute; odds and schedule results every 5 minutes; team summaries hourly.")
    with st.expander("Use your own files"):
        mode = st.radio("Schedule source", ["Automatic download", "Upload CSV"])
        schedule_file = st.file_uploader("Schedule CSV", type="csv") if mode == "Upload CSV" else None
        current_file = st.file_uploader(f"{season} team summaries", type="csv")
        prior_file = st.file_uploader(f"{season - 1} team summaries", type="csv")
    st.caption(f"Prediction model {MODEL_VERSION}")

if mode == "Upload CSV" and schedule_file is None:
    st.info("Upload a schedule or select Automatic download.")
    st.stop()
try:
    schedule = pd.read_csv(schedule_file, low_memory=False) if schedule_file is not None else download_schedule(season)
    original_schedule = schedule.copy()
    required = {"season", "week", "home_id", "away_id", "home_team", "away_team", "home_points", "away_points"}
    missing = required - set(schedule.columns)
    if missing:
        raise ValueError("Missing schedule columns: " + ", ".join(sorted(missing)))
    schedule = schedule.copy()
    schedule = schedule[pd.to_numeric(schedule["season"], errors="coerce") == season]
    if "season_type" in schedule:
        schedule = schedule[schedule["season_type"].astype(str).str.lower() == "regular"]
    schedule = normalize_fbs_schedule(schedule)
    for col in ["week", "home_id", "away_id", "home_points", "away_points"]:
        schedule[col] = pd.to_numeric(schedule[col], errors="coerce")
    schedule = schedule.dropna(subset=["week", "home_id", "away_id"])
    schedule = schedule[schedule["week"] >= 1]
    for col in ["completed", "neutral_site"]:
        if col in schedule:
            schedule[col] = schedule[col].astype(str).str.lower().isin(["true", "t", "1", "1.0", "yes", "y"])
    if "start_date" in schedule:
        schedule = schedule.sort_values("start_date", kind="stable")
except Exception as exc:
    st.error(f"Could not load the {season} schedule: {exc}")
    st.info("Try Refresh all data, another season, or Upload CSV.")
    st.stop()
if schedule.empty:
    st.warning(f"No regular-season FBS matchups available for {season}.")
    st.stop()

weeks = sorted(schedule["week"].astype(int).unique().tolist())
default_week = weeks[-1]
if "start_date" in schedule:
    dates = pd.to_datetime(schedule["start_date"], errors="coerce", utc=True)
    upcoming = schedule[dates >= pd.Timestamp.now(tz="UTC")]
    if "completed" in upcoming:
        upcoming = upcoming[~upcoming["completed"]]
    if not upcoming.empty:
        default_week = int(upcoming.iloc[0]["week"])
with week_col:
    selected_week = st.selectbox("Week", weeks, index=weeks.index(default_week), format_func=lambda w: f"Week {w}")
games = schedule[schedule["week"] == selected_week]
dashboard_summary = st.empty()
export_controls = st.container()
if st.session_state.get("main_app_tabs") == "Compare picks":
    st.session_state["main_app_tabs"] = "Game cards"
cards_tab, risky_tab, value_tab, performance_tab, scenario_tab, parlay_tab, tracker_tab, about_tab = st.tabs(["Game cards", "Risky picks", "Value shortlist", "Model results", "What-if bets", "Parlay finder", "My bets", "How it works"], key="main_app_tabs", on_change="rerun")
with about_tab:
    feed_details = st.expander("Feed health & data notes", expanded=False)

try:
    with st.spinner("Loading team statistics and generating predictions..."):
        current = read_summary(current_file, season)
        prior = read_summary(prior_file, season - 1)
        published_current = current.copy()
        current, derived_team_data = augment_missing_summaries(current, prior, schedule, selected_week)
except Exception as exc:
    st.error(f"Could not load team summaries: {exc}")
    st.info("Try Refresh all data. If the selected season is not published yet, choose an available season or supply CSV overrides.")
    st.stop()

with feed_details:
    eligible = current[current["through_week"] < selected_week]
    missing_team_ids = set()
    missing_team_names = []
    derived_team_ids = set(derived_team_data)
    if derived_team_ids:
        derived_names = {}
        for _, game in games.iterrows():
            derived_names[int(game["home_id"])] = str(game["home_team"])
            derived_names[int(game["away_id"])] = str(game["away_team"])
        derived_list = sorted(derived_names[tid] for tid in derived_team_ids if tid in derived_names)
        st.info(f"Schedule-derived fallback statistics are being used for: {', '.join(derived_list)}. These provisional metrics combine prior profiles with completed-game scoring data until the advanced summary feed catches up.")
    if selected_week > 1:
        team_ids = set(games["home_id"]) | set(games["away_id"])
        missing_team_ids = team_ids - set(eligible["team_id"])
        if missing_team_ids:
            names = {}
            for _, game in games.iterrows():
                names[int(game["home_id"])] = str(game["home_team"])
                names[int(game["away_id"])] = str(game["away_team"])
            missing_team_names = sorted(names[tid] for tid in missing_team_ids if tid in names)
            st.warning(f"{len(missing_team_names)} team{'s' if len(missing_team_names) != 1 else ''} have no published pregame statistics for this week: {', '.join(missing_team_names)}. Their predictions use the model's prior-data fallback.")
            st.caption("A team may have played without having updated pregame metrics. FCS opponents are excluded from the schedule-based fallback, so a team whose only completed games were against FCS opponents (such as Northwestern in Week 3) has no qualifying scoring data for that fallback. Advanced team-summary data can also be delayed or missing. These picks rely on prior data until eligible current-season metrics are available.")
        if not eligible.empty and eligible["through_week"].max() < selected_week - 1:
            st.warning(f"Published statistics currently extend through week {int(eligible['through_week'].max())}. Predictions use the latest available pregame snapshot.")
try:
    pred = predict_all_games(current, prior, schedule, selected_week)
except Exception as e:
    st.error(str(e))
    st.stop()

if pred.empty:
    st.info("No predictions are available for this week. Try another week above.")
    st.stop()

date_range = None
odds_snapshot = {"quotes": {}, "retrieved": None}
if "start_date" in games:
    dates = pd.to_datetime(games["start_date"], errors="coerce", utc=True).dropna()
    if not dates.empty and (dates.max() - dates.min()).days <= 30:
        date_range = dates.min().strftime("%Y%m%d") + "-" + dates.max().strftime("%Y%m%d")
live_snapshot = {"games": {}, "retrieved": None}
if date_range:
    try:
        live_snapshot = download_live_scores(date_range, schedule_event_ids(games))
        st.session_state["live_scores_" + date_range] = live_snapshot
    except Exception:
        live_snapshot = st.session_state.get("live_scores_" + date_range, live_snapshot)
        st.warning("Live scoreboard is temporarily unavailable. Last loaded scores may be stale.")
if live_snapshot.get("missing_event_ids"):
    st.warning(f"Could not refresh {len(live_snapshot['missing_event_ids'])} game result(s). Their schedule status is shown until the next refresh.")
live_games = overlay_live_scores(games, live_snapshot["games"])
pred = attach_results(pred, live_games)
if live_snapshot["retrieved"]:
    feed_details.caption("Live scores via ESPN · last retrieved " + live_snapshot["retrieved"] + ". Updates about every minute while open; feed delays are possible. Predictions remain pregame estimates.")

if date_range:
    try:
        odds_snapshot = download_market_odds(date_range, schedule_event_ids(games))
    except Exception:
        st.info("DraftKings odds are temporarily unavailable. Predictions and results are still available.")
pred = add_betting_value(attach_odds(pred, games, odds_snapshot["quotes"]))
try:
    waterfall_boxes = download_advantage_boxes(season)
except Exception:
    waterfall_boxes = pd.DataFrame()
    st.warning("Tiers 1–4 are unavailable because FBS box scores could not be loaded. Tier 5 can still use the published weekly team-summary snapshot.")
weather_checks = {}
weather_candidates = []
try:
    week_weather_ids = tuple(
        int(gid) for gid in pd.to_numeric(pred.get("Game ID"), errors="coerce").dropna().astype(int).unique()
    )
    if week_weather_ids:
        weather_checks = value_weather_context(schedule, selected_week, week_weather_ids)
except Exception:
    weather_checks = {}
if not waterfall_boxes.empty:
    try:
        weather_profiles = build_waterfall_profiles(schedule, waterfall_boxes, selected_week)
        weather_candidates = weather_tier_candidate_ids(pred, schedule, weather_profiles)
    except Exception:
        weather_candidates = []
if weather_candidates:
    missing_weather = sum(
        weather_checks.get(str(int(gid)), {}).get("status") not in ("ok", "indoor")
        for gid in weather_candidates
    )
    if missing_weather:
        st.warning(
            f"Tier 2 weather could not be verified for {missing_weather} candidate game(s). "
            "Those games are excluded from the Storm Front tier."
        )
pred = add_waterfall_value(pred, schedule, waterfall_boxes, selected_week, weather_checks=weather_checks, published_summary=published_current)
line_history = st.session_state.setdefault("moneyline_observations_v1", {})
if st.session_state.get("moneyline_history_season") != season:
    line_history.clear()
    st.session_state["moneyline_history_season"] = season
pred["Line Movement HTML"] = [line_movement_html(row, line_history, odds_snapshot["retrieved"]) for _, row in pred.iterrows()]
if odds_snapshot.get("lookup_errors"):
    st.warning(f"Individual odds lookups failed for {len(odds_snapshot['lookup_errors'])} games. Missing lines may reflect a retrieval error; try Refresh all feeds now.")
feed_details.caption(f"Market coverage: {int(pred['Bet Line'].ne('Unavailable').sum())} of {len(pred)} model picks have a moneyline; {int(pred['Home Spread'].ne('Unavailable').sum())} of {len(pred)} matchups have a spread. Unavailable means no matching price was retrieved from the connected feeds.")
weather_ok = sum(1 for wx in weather_checks.values() if wx.get("status") in ("ok", "indoor"))
feed_details.caption(
    f"Weather coverage: {weather_ok} of {len(pred)} matchups resolved. Outdoor forecasts use the kickoff hour through four hours after kickoff; indoor venues are labeled separately."
)

awaiting_count = int(pred["Status"].ne("Final").sum())
value_count = int(pred["Value Selected"].sum())
high_count = int((pred["Confidence"] >= .8).sum())
close_count = int((pred["Confidence"] < .6).sum())
graded = pred[pred["Pick Result"].isin(["Correct", "Incorrect"])]
correct_count = int(graded["Pick Result"].eq("Correct").sum())
accuracy = f"{correct_count / len(graded):.1%}" if len(graded) else "—"
week_state = "All games final" if awaiting_count == 0 else f"{awaiting_count} awaiting final"
dashboard_summary.markdown(f"""<section class="week-dashboard"><div class="week-heading"><div><span class="section-kicker">{season} SEASON</span><h2>Week {selected_week}</h2></div><span class="week-state">{week_state}</span></div><div class="dashboard-metrics"><div><strong>{len(pred)}</strong><span>Matchups</span></div><div><strong>{correct_count}–{len(graded)-correct_count}</strong><span>Pick record</span></div><div><strong>{accuracy}</strong><span>Graded accuracy</span></div><div><strong>{value_count}</strong><span>Model value picks</span></div></div></section>""", unsafe_allow_html=True)
with feed_details:
    schedule_time = original_schedule.attrs.get("fetched_at", "Uploaded CSV" if schedule_file is not None else "Unknown")
    stats_time = published_current.attrs.get("fetched_at", "Uploaded CSV" if current_file is not None else "Unknown")
    st.caption(f"Last fetched · Scores: {schedule_time} · Odds: {odds_snapshot['retrieved'] or 'Unavailable'} · Team stats: {stats_time}")
    st.caption("Fetch times show when the app retrieved the feeds, not when the provider updated them. Live scores refresh about every minute while open; schedule and odds every 5 minutes; team stats hourly.")
    if st.button("Refresh all feeds now"):
        download_summary.clear()
        download_advantage_boxes.clear()
        download_live_scores.clear()
        download_live_event.clear()
        download_schedule.clear()
        download_market_odds.clear()
        download_archived_event.clear()
        download_event_moneylines.clear()
        value_weather_context.clear()
        st.rerun()
    st.caption("Historical picks are recalculated from pregame-week statistics, not a saved record of picks issued before kickoff. Pending games and ties do not count toward accuracy.")
    st.caption("DraftKings moneylines and spreads via ESPN, with another sportsbook shown when DraftKings is unavailable · American odds · Unavailable means no matching line is published. Verify the price in DraftKings before placing a bet.")
    if odds_snapshot["retrieved"]:
        st.caption(f"Odds retrieved {odds_snapshot['retrieved']}. Completed-game moneylines are archived prices; they are not available to bet now.")
    st.caption("Weather via Open-Meteo using ESPN venue metadata. Forecasts are cached for 15 minutes and can change as kickoff approaches.")
    st.caption("Confidence is the model’s estimated chance that its pick wins. Even high-confidence picks can lose.")
with value_tab:
    st.markdown(
        """
        <h3 style="margin:0 0 12px 0; white-space:nowrap;">
            Value Picks · Five-stage waterfall
        </h3>
        """,
        unsafe_allow_html=True,
    )
    value_picks = pred[pred["Value Selected"]].sort_values("Value Rank")
    if len(value_picks) < 12:
        st.info(f"{12-len(value_picks)} below target. No gates or odds limits were relaxed.")
    with st.expander("How Value Picks are selected", expanded=False):
        tier_guide = [
            (
                "1",
                "Complete Game",
                "The home team leads in all five matchup measures: rushing, passing, run defense, pass defense, and turnover margin. Home field completes the six advantages.",
                "10–4 ATS",
            ),
            (
                "2",
                "Storm Front",
                "Bad weather favors a home team with stronger run defense and a better turnover margin. Teams favored by 14 points or more are excluded.",
                "12–2–1 ATS",
            ),
            (
                "3",
                "Takeaway Trouble",
                "A Power Four underdog has a turnover-margin advantage of at least one per game. The opposing favorite must be priced from −110 to −150.",
                "23–9",
            ),
            (
                "4",
                "The Foundation",
                "Week 4 or later, a regular-season FBS favorite priced from −505 through −1000 qualifies as a straight-up pick. No model-confidence or matchup-stat gate is required.",
                "39–0",
            ),
            (
                "5",
                "Home Turf Hammer",
                "In a Power Four matchup, the home team leads in red-zone offense, red-zone defense, explosive offense, and limiting explosive plays. Uses the prior week’s published stats.",
                "42–11",
            ),
        ]
        st.markdown("""
<style>
.cfb-tier-guide {display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:12px;margin:4px 0 14px;}
.cfb-tier-guide-card {border:1px solid #58ae8745;border-radius:14px;padding:16px;background:#58ae8709;}
.cfb-tier-guide-heading {display:flex;align-items:center;gap:10px;margin-bottom:8px;}
.cfb-tier-guide-number {display:inline-flex;align-items:center;justify-content:center;flex:0 0 28px;height:28px;border-radius:8px;background:#58ae8725;color:#74bfa0;font-size:14px;font-weight:700;}
.cfb-tier-guide-title {font-size:17px;font-weight:700;line-height:1.3;}
.cfb-tier-guide-copy {font-size:14px;line-height:1.6;opacity:.85;margin:0;}
.cfb-tier-guide-record-label {font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;opacity:.65;margin:14px 0 7px;}
.cfb-tier-guide-records {display:flex;flex-wrap:wrap;gap:7px;}
.cfb-tier-guide-record {display:inline-flex;gap:6px;align-items:center;border:1px solid #58ae8755;border-radius:999px;padding:5px 9px;background:#58ae8712;font-size:12px;line-height:1.2;}
.cfb-tier-guide-record strong {font-size:12px;}
</style>
""" + '<div class="cfb-tier-guide">' + "".join(
            f'<div class="cfb-tier-guide-card"><div class="cfb-tier-guide-heading">'
            f'<span class="cfb-tier-guide-number">{number}</span>'
            f'<span class="cfb-tier-guide-title">{escape(title)}</span></div>'
            f'<p class="cfb-tier-guide-copy">{escape(description)}</p>'
            f'<div class="cfb-tier-guide-record-label">Historical record</div>'
            f'<div class="cfb-tier-guide-records">'
            f'<span class="cfb-tier-guide-record"><strong>{escape(record)}</strong></span>'
            f'</div></div>'
            for number, title, description, record in tier_guide
        ) + '</div>', unsafe_allow_html=True)
        st.caption("Tier numbers show selection order, not win probability. See Recommended Bet for the play.")
        st.caption("Historical selections are recalculated from archived data; they are not saved pregame picks.")
    if not value_picks.empty:
        value_show = value_picks.copy()
        value_show["Matchup"] = value_show["Away Team"] + " at " + value_show["Home Team"]
        value_show["Recommended Bet"] = np.where(
            value_show["Value Market"].eq("Spread"),
            value_show["Value Pick"].astype(str) + " " + value_show["Value Line"].astype(str) + " ATS",
            value_show["Value Pick"].astype(str) + " ML " + value_show["Value Line"].astype(str),
        )
        st.dataframe(value_show[["Value Rank", "Value Tier", "Recommended Bet", "Value Result", "Value Price", "Value Source", "Matchup", "Status"]], hide_index=True, use_container_width=True, column_config={"Value Result": st.column_config.TextColumn("Results", pinned=True)})
        graded_value = value_picks[value_picks["Value Result"].isin(["Correct", "Incorrect"])]
        if not graded_value.empty:
            wins = int(graded_value["Value Result"].eq("Correct").sum())
            st.caption(f"Recalculated selections: {wins}–{len(graded_value)-wins} ({wins/len(graded_value):.1%}). Core-model results are reported separately.")
    else:
        st.info("No games qualify with verified FBS histories and available market prices.")
def sort_picks_by_game_time(picks, schedule):
    """Earliest kickoff first; unknown times last, without changing export columns."""
    starts = schedule[["game_id", "start_date"]].copy()
    starts["game_id"] = pd.to_numeric(starts["game_id"], errors="coerce")
    starts = starts.dropna(subset=["game_id"]).drop_duplicates("game_id")
    kickoff_by_id = pd.to_datetime(starts.set_index("game_id")["start_date"], utc=True, errors="coerce")
    ordered = picks.copy()
    ordered["_kickoff_sort"] = pd.to_numeric(ordered["Game ID"], errors="coerce").map(kickoff_by_id)
    return ordered.sort_values("_kickoff_sort", kind="stable", na_position="last").drop(columns="_kickoff_sort")


def reset_pick_filters():
    defaults = {"pick_query": "", "pick_level": "All confidence levels",
                "pick_order": "Highest confidence", "pick_status": "All games",
                "pick_odds": "All odds", "pick_quality": "All data",
                "pick_favorites_only": False}
    for key, value in defaults.items():
        st.session_state[key] = value


with cards_tab:
    tour_at("filters")
    st.subheader("Matchup center")
    st.caption("Search your team or browse the slate. Open a card’s details for the full analysis.")
    search_col, confidence_col, sort_col = st.columns([2, 1, 1])
    with search_col:
        query = st.text_input("Find a team", placeholder="Search LSU, Texas, Ohio State…", key="pick_query")
    with confidence_col:
        level = st.selectbox("Confidence", ["All confidence levels", "High · 80%+", "Moderate · 70–80%", "Lean · 60–70%", "Toss-up · under 60%"], key="pick_level")
    with sort_col:
        order = st.selectbox("Sort by", ["Highest confidence", "Closest matchups", "Game time", "Home team A–Z"], key="pick_order")
    with st.expander("Favorite teams & saved filters", expanded=False):
        team_choices = sorted(set(schedule["home_team"]) | set(schedule["away_team"]))
        favorite_choices = sorted(set(team_choices) | set(st.session_state.get("favorite_teams", [])))
        favorites = st.multiselect("Favorite teams", favorite_choices, key="favorite_teams",
                                   help="Saved during this app session. Choose teams, then turn on Favorites only.")
        st.checkbox("Favorites only", key="pick_favorites_only")
        st.button("Reset filters", on_click=reset_pick_filters,
                  help="Resets matchup filters and keeps your favorite-team list.")
    filtered = pred.copy()
    if query.strip():
        matched = filtered["Home Team"].str.contains(query.strip(), case=False, regex=False) | filtered["Away Team"].str.contains(query.strip(), case=False, regex=False)
        filtered = filtered[matched]
    bands = {"High · 80%+": (.8, 1.01), "Moderate · 70–80%": (.7, .8), "Lean · 60–70%": (.6, .7), "Toss-up · under 60%": (0, .6)}
    if level in bands:
        low, high = bands[level]
        filtered = filtered[(filtered["Confidence"] >= low) & (filtered["Confidence"] < high)]
    if order == "Closest matchups":
        filtered = filtered.sort_values("Confidence")
    elif order == "Game time":
        filtered = sort_picks_by_game_time(filtered, games)
    elif order == "Home team A–Z":
        filtered = filtered.sort_values("Home Team")
    status_filter = st.radio("Game results", ["All games", "In progress", "Final", "Awaiting final", "Correct picks", "Incorrect picks"], horizontal=True, key="pick_status")
    if status_filter == "In progress":
        filtered = filtered[filtered["Status"].eq("In progress")]
    elif status_filter == "Final":
        filtered = filtered[filtered["Status"].eq("Final")]
    elif status_filter == "Awaiting final":
        filtered = filtered[~filtered["Status"].eq("Final")]
    elif status_filter in ["Correct picks", "Incorrect picks"]:
        filtered = filtered[filtered["Pick Result"].eq(status_filter.split()[0])]
    
    with st.expander("More filters · odds & team data", expanded=False):
        odds_col, data_col = st.columns(2)
        with odds_col:
            odds_filter = st.selectbox("Moneylines", ["All odds", "Pick has moneyline", "Pick missing moneyline"], key="pick_odds")
        with data_col:
            quality_filter = st.selectbox("Team data", ["All data", "Both teams have published stats", "Includes score estimates", "Includes prior data only"], key="pick_quality")
    if st.session_state.get("pick_favorites_only"):
        filtered = filtered[filtered["Home Team"].isin(favorites) | filtered["Away Team"].isin(favorites)]
        if not favorites:
            st.info("Select a favorite team above to see its matchups.")
    if odds_filter == "Pick has moneyline":
        filtered = filtered[filtered["Bet Line"].ne("Unavailable")]
    elif odds_filter == "Pick missing moneyline":
        filtered = filtered[filtered["Bet Line"].eq("Unavailable")]
    published_ids = set(published_current.loc[published_current["through_week"] < selected_week, "team_id"].astype(int))
    quality_by_match = {}
    for _, quality_game in games.iterrows():
        ids = {int(quality_game["home_id"]), int(quality_game["away_id"])}
        quality_by_match[(quality_game["home_team"], quality_game["away_team"])] = (
            ids.issubset(published_ids),
            bool(ids & set(derived_team_data)),
            bool(ids - published_ids - set(derived_team_data)),
        )
    if quality_filter != "All data":
        quality_index = {"Both teams have published stats": 0, "Includes score estimates": 1, "Includes prior data only": 2}[quality_filter]
        keep = [quality_by_match.get((r["Home Team"], r["Away Team"]), (False, False, True))[quality_index] for _, r in filtered.iterrows()]
        filtered = filtered.loc[pd.Series(keep, index=filtered.index, dtype=bool)]
    st.caption("Published stats means a pregame summary exists; individual metrics may still be missing.")
    st.caption(f"Showing {len(filtered)} of {len(pred)} predictions · {season} regular season · FBS vs. FBS")
    
with export_controls:
    tour_at("export")
    with st.popover("Export picks", icon=":material/download:"):
        st.caption(f"{season} · Week {selected_week} · CSV for Excel")
        st.download_button(
            f"All picks for this week ({len(pred)})",
            pred.drop(columns=["Line Movement HTML"], errors="ignore").to_csv(index=False).encode("utf-8-sig"),
            file_name=f"cfb_{season}_{MODEL_VERSION}_week_{selected_week}_all_picks.csv",
            mime="text/csv", disabled=pred.empty, key="export_all_picks", on_click="ignore",
        )
        st.download_button(
            f"Currently filtered picks ({len(filtered)})",
            filtered.drop(columns=["Line Movement HTML"], errors="ignore").to_csv(index=False).encode("utf-8-sig"),
            file_name=f"cfb_{season}_{MODEL_VERSION}_week_{selected_week}_filtered_picks.csv",
            mime="text/csv", disabled=filtered.empty, key="export_filtered_picks", on_click="ignore",
        )
        st.caption("Filtered picks follow the search and filters in Game cards.")

with cards_tab:
    tour_at("cards")
    with st.expander("Understanding line-movement flags", expanded=False):
        st.caption("↔ Moneyline moved compares the same sportsbook’s opening and latest prices. Expand the flag for details. Session changes are tracked while this app session is active; no net change does not mean the line never moved. Fetch times are not the sportsbook’s change times. Shortened = higher implied chance and lower payout; lengthened = the reverse.")
    if filtered.empty:
        st.info("No matchups match these filters. Clear your search or choose another confidence level.")
    if not pred.empty:
        cards = {}
        card_details = {}
        risky_indices = []
        try:
            advantage_checks = build_advantages(schedule, download_advantage_boxes(season), selected_week)
            advantage_error = "Not enough earlier-week FBS data."
        except (OSError, ValueError, KeyError, TypeError):
            advantage_checks = {}
            advantage_error = "Pregame box-score feed unavailable. Try Refresh all data; missing data is not a risk rating."
        logo_urls = tuple(sorted({
            url for column in ("away_id", "home_id")
            for team_id in games[column] if (url := team_logo_url(team_id))
        }))
        logo_sources = embedded_team_logos(logo_urls)
        rz_index = {}
        if pred["Confidence"].lt(.80).any():
            try:
                rz_index = red_zone_team_index(season)
            except (OSError, ValueError):
                pass
        rz_cards = {}
        if rz_index:
            def load_rz_card(item):
                idx, pick = item
                match = games[(games["home_team"] == pick["Home Team"]) & (games["away_team"] == pick["Away Team"])]
                return idx, red_zone_matchup_html(pick, match, schedule, season, selected_week, rz_index)
            with st.spinner("Checking red-zone matchup data..."):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    rz_cards = dict(pool.map(load_rz_card, list(pred[pred["Confidence"].lt(.80)].iterrows())))
        for card_idx, r in pred.iterrows():
            badge_class = "badge close" if r["Confidence"] < .7 else "badge"
            risk = '<div class="risk-note">Away-team pick · ' + escape(str(r["Venue Risk"])) + ' venue risk</div>' if r["Venue Risk"] != "Normal" else ""
            venue = "Neutral site" if r["Neutral Site"] else "Away at home"
            outcome_class = "badge" if r["Pick Result"] == "Correct" else "badge incorrect" if r["Pick Result"] == "Incorrect" else "badge close"
            outcome = f'<div class="result-box"><span class="{outcome_class}">{escape(str(r["Pick Result"]))}</span><div class="result-score">{escape(str(r["Status"]))} · {escape(str(r["Final Score"]))}</div><div>Actual winner: <strong>{escape(str(r["Actual Winner"]))}</strong></div></div>'
            moneylines = betting_odds_html(r)
            game = games[(games["home_team"] == r["Home Team"]) & (games["away_team"] == r["Away Team"])]
            game_weather = {}
            if len(game) == 1 and pd.notna(game.iloc[0].get("game_id")):
                game_weather = weather_checks.get(str(int(game.iloc[0]["game_id"])), {})
            weather_html = weather_card_html(game_weather)
            missing_data_note = ""
            if len(game) == 1:
                absent = []
                if int(game.iloc[0]["home_id"]) in missing_team_ids:
                    absent.append(str(r["Home Team"]))
                if int(game.iloc[0]["away_id"]) in missing_team_ids:
                    absent.append(str(r["Away Team"]))
                if absent:
                    missing_data_note = '<div class="risk-note">Updated pregame metrics unavailable: ' + escape(", ".join(absent)) + ' · prior-data fallback. FCS games are excluded from the scoring fallback; advanced summaries may also be delayed or missing.</div>'
            away_logo = team_logo_url(game.iloc[0]["away_id"]) if len(game) == 1 else ""
            home_logo = team_logo_url(game.iloc[0]["home_id"]) if len(game) == 1 else ""
            away_alt = escape(str(r["Away Team"]), quote=True)
            home_alt = escape(str(r["Home Team"]), quote=True)
            away_logo_html = f'<img class="team-logo" src="{logo_sources.get(away_logo, away_logo)}" alt="{away_alt} logo" width="34" height="34" />' if away_logo else ""
            home_logo_html = f'<img class="team-logo" src="{logo_sources.get(home_logo, home_logo)}" alt="{home_alt} logo" width="34" height="34" />' if home_logo else ""
            home_badge, away_badge = "", ""
            if len(game) == 1:
                for data_side in ("home", "away"):
                    data_label, _, _ = team_data_details(game.iloc[0][data_side + "_id"], published_current, derived_team_data, selected_week)
                    if data_label != "Advanced stats":
                        data_badge = '<span class="badge close" style="display:inline-block;margin-top:5px">' + escape(data_label) + '</span>'
                        if data_side == "home":
                            home_badge = data_badge
                        else:
                            away_badge = data_badge
            kickoff = "Kickoff time TBD"
            if len(game) == 1:
                date = pd.to_datetime(game.iloc[0].get("start_date"), errors="coerce", utc=True)
                if pd.notna(date):
                    kickoff = date.tz_convert("America/Chicago").strftime("%a, %b %d · %I:%M %p %Z")
            if r["Status"] != "Final":
                detail = str(r.get("Live Detail", ""))
                score = str(r.get("Live Score", "—"))
                label = "LIVE · " + detail if r["Status"] == "In progress" else (detail if any(word in detail.lower() for word in ("delay", "postpon", "cancel", "suspend")) else str(r["Status"]))
                outcome = '<div class="result-box"><strong>' + escape(label) + '</strong>'
                if score != "—":
                    outcome += '<div class="result-score">' + escape(score) + '</div>'
                outcome += '</div>' 
            explanation = r.get("Pick Explanation", "")
            if not isinstance(explanation, str) or not explanation.strip():
                explanation = (
                    f"The model picks {r['Predicted Winner']} with a {r['Confidence']:.0%} estimated chance to win. "
                    "A breakdown of the contributing factors is currently unavailable."
                )
            caveats = []
            if len(game) == 1:
                for side_name in ("home", "away"):
                    tid = int(game.iloc[0][side_name + "_id"])
                    name = str(game.iloc[0][side_name + "_team"])
                    if tid in derived_team_ids:
                        caveats.append(name + " uses provisional scoring-based metrics")
                    elif tid not in set(eligible["team_id"]):
                        caveats.append(name + " has no eligible current-season metrics")
            if caveats:
                explanation += " Data note: " + "; ".join(caveats) + "."
            explanation_html = (
                '<div class="pick-summary"><strong>Why we picked them</strong><p>'
                + escape(explanation) + '</p></div>'
            )
            matchup_html = matchup_insights_html(r, game, published_current, schedule, selected_week, derived_team_ids)
            red_zone_html = rz_cards.get(card_idx, "")
            if red_zone_html:
                matchup_html = matchup_html.replace("</details>", red_zone_html + "</details>")
            check = advantage_checks.get(str(int(game.iloc[0]['game_id'])), {"status":"missing", "reason":advantage_error}) if len(game) == 1 else {"status":"missing", "reason":"Game could not be matched."}
            summary_side = "home" if r["Predicted Side"] == "Home" else "away"
            summary_opponent = r["Away Team"] if summary_side == "home" else r["Home Team"]
            explanation_html += matchup_strengths_html(
                check, summary_side, str(r["Predicted Winner"]), str(summary_opponent)
            )
            is_tiered = bool(r.get("Value Selected", False))
            confidence_value = pd.to_numeric(r.get("Confidence"), errors="coerce")
            is_high_confidence = pd.notna(confidence_value) and float(confidence_value) >= 0.80
            advantage_note = advantage_html(
                check,
                "home" if r["Predicted Side"] == "Home" else "away",
                r["Predicted Winner"],
                suppress_risk=is_tiered or is_high_confidence,
            )
            scored = assess(check, "home" if r["Predicted Side"] == "Home" else "away")
            is_risky = should_flag_risky(scored, is_tiered, confidence_value)
            if is_risky:
                risky_indices.append(card_idx)
            warning = ('<div style="display:flex;align-items:center;gap:12px;padding:12px 14px;margin-bottom:12px;border:2px solid #e9a23b;border-radius:10px;background:#e9a23b20"><span aria-hidden="true" style="display:inline-flex;align-items:center;justify-content:center;flex:0 0 32px;height:32px;border-radius:50%;background:#e9a23b;color:#171717;font-size:25px;font-weight:900">!</span><div><strong>RISKY PICK · MATCHUP WARNING</strong><br><span>' + str(scored["count"]) + '/5 advantages for ' + escape(str(r["Predicted Winner"])) + '</span></div></div>') if is_risky else ""
            gotw_note = ""
            if bool(r.get("Game of Week", False)):
                gotw_team = escape(str(r.get("Game of Week Team", "")))
                gotw_tiers = escape(str(r.get("Game of Week Tiers", "")))
                gotw_note = (
                    '<div class="gotw-banner">'
                    '<div class="gotw-kicker">🏆 Game of the Week · Cross-tier consensus</div>'
                    f'<div class="gotw-pick">{gotw_team}</div>'
                    f'<div class="gotw-tiers">{gotw_tiers}</div>'
                    '</div>'
                )
            waterfall_note = ('<div class="result-box"><strong>' + escape(str(r['Value Tier'])) + '</strong><div>' + escape(str(r['Value Pick'])) + ' · ' + escape(str(r.get('Value Market', ''))) + ' ' + escape(str(r['Value Line'])) + ' · ' + escape(str(r.get('Value Source', 'Unavailable'))) + '</div></div>') if r.get('Value Selected', False) else ''
            card_details[card_idx] = (
                explanation_html + warning + advantage_note
                + str(r.get("Line Movement HTML", "")) + matchup_html
                + f'<div class="card-details"><strong>Prediction details</strong>'
                + f'<p>Model {escape(str(r["Model Version"]))} · {escape(venue)}. '
                + 'Confidence is an estimate, not a guaranteed result.</p>'
                + risk + missing_data_note + '</div>'
            )
            cards[card_idx] = f"""<article class="pick-card">{gotw_note}
<div class="card-top"><span>{venue}</span><span class="{badge_class}">{escape(str(r['Confidence Label']))}</span></div>
<div class="kickoff">{escape(kickoff)}</div>
{weather_html}
<div class="team-line"><div class="team-name"><span class="venue-label">Away</span><span class="team-identity">{away_logo_html}{escape(str(r['Away Team']))}</span>{away_badge}</div><strong>{r['Away Win %']:.1%}</strong></div>
<div class="team-line"><div class="team-name"><span class="venue-label">Home</span><span class="team-identity">{home_logo_html}{escape(str(r['Home Team']))}</span>{home_badge}</div><strong>{r['Home Win %']:.1%}</strong></div>
<div class="pick-result"><div class="pick-label">Predicted winner</div><div class="pick-winner">{escape(str(r['Predicted Winner']))}</div>
<div class="conf-row"><span>Win confidence</span><strong>{r['Confidence']:.1%}</strong></div>
<div class="conf-track"><div class="conf-fill" style="width:{r['Confidence'] * 100:.1f}%"></div></div></div>{moneylines}{waterfall_note}{outcome}</article>"""
        def render_pick_cards(rows, prefix):
            for card_index, (row_id, pick) in enumerate(rows.iterrows()):
                if card_index % 2 == 0:
                    card_columns = st.columns(2, gap="medium")
                card = cards[row_id].replace('<article class="pick-card">', '').replace('</article>', '')
                card = card.replace("<!--away-data-->", "").replace("<!--home-data-->", "")
                matchup = games[(games["home_team"] == pick["Home Team"]) & (games["away_team"] == pick["Away Team"])]
                with card_columns[card_index % 2], st.container(border=True, key=f"{prefix}_card_{season}_{selected_week}_{card_index}"):
                    st.markdown(card, unsafe_allow_html=True)
                    with st.expander("Details", expanded=False):
                        st.markdown(card_details[row_id], unsafe_allow_html=True)
                        st.markdown("**Team statistics & data quality**")
                        for side in ("away", "home"):
                            tid = matchup.iloc[0][side + "_id"] if len(matchup) == 1 else None
                            label, note, metrics = team_data_details(tid, published_current, derived_team_data, selected_week)
                            st.markdown(f"**{pick[side.title() + ' Team']} · {label}**")
                            st.caption(note)
                            for metric, value in metrics.items():
                                st.write(f"**{metric}:** {value}")
        gotw_mask = filtered.get("Game of Week", pd.Series(False, index=filtered.index)).fillna(False).astype(bool)
        gotw_rows = filtered.loc[gotw_mask].copy()
        other_rows = filtered.loc[~gotw_mask].copy()
        if not gotw_rows.empty:
            if order != "Game time":
                gotw_rows = gotw_rows.sort_values(
                    ["Game of Week Tier Count", "Confidence"],
                    ascending=[False, False],
                    kind="stable",
                )
            st.markdown("#### 🏆 Games of the Week")
            st.caption("Cross-tier consensus · two or more eligible tiers (1, 2, 3, or 5) independently point to the same team. Tier 4 is excluded, and the consensus team's DraftKings moneyline must be -300 or longer.")
            render_pick_cards(gotw_rows, "gotw")
            if not other_rows.empty:
                st.markdown("#### All other matchups")
                render_pick_cards(other_rows, "matchup")
        else:
            render_pick_cards(filtered, "matchup")
        with risky_tab:
            tour_at("risky")
            st.subheader(f"Risky picks · {len(risky_indices)}")
            st.caption(f"All flagged picks for {season}, Week {selected_week}. Game-card filters do not limit this list.")
            st.write("A warning means a non-tiered pick below 80% model confidence has 0, 1 or 2 of the five matchup advantages. Official Tier 1–5 Value Picks and High/Very High confidence picks (80%+) are excluded so the labels never contradict each other. Applies to P4 vs. P4 (including Notre Dame) and G6 vs. G6.")
            if not advantage_checks:
                st.info(advantage_error)
            elif risky_indices:
                render_pick_cards(pred.loc[risky_indices], "risky")
            else:
                st.info("No non-tiered picks below 80% confidence meet the risk threshold this week.")
            st.caption("Tiered games, High/Very High confidence picks (80%+), and games with missing metrics are not rated as risky. No warning does not mean a safe bet. Picks and model confidence are unchanged.")
with performance_tab:
    show_shadow_tracking(st, season, selected_week)
    tour_at("results")
    st.subheader("Model results by confidence")
    st.caption("All model picks in the chosen period, independent of matchup filters, moneyline availability, or your personal bets. Accuracy measures picking the winner, not betting profit.")
    performance_scope = st.radio("Results period", ["Selected week", "Season to date"], horizontal=True, key="model_results_period")
    performance_frames = []
    value_performance_frames = []
    performance_errors = []
    value_performance_errors = []
    results_schedule = overlay_live_scores(schedule, live_snapshot["games"])

    if performance_scope == "Selected week":
        performance_frames = [pred]
        if selected_week >= 3:
            value_performance_frames = [pred]
    else:
        completed_mask = results_schedule.get("completed", pd.Series(False, index=results_schedule.index)).astype(str).str.lower().isin(["true", "t", "1", "1.0", "yes", "y"])
        result_weeks = sorted(results_schedule.loc[completed_mask, "week"].astype(int).unique().tolist())
        st.caption("Season to date includes weeks with at least one completed game; any unfinished games in those weeks remain ungraded.")
        with st.spinner("Calculating model and Value Pick results from pregame-week statistics..."):
            for result_week in result_weeks:
                try:
                    if result_week == selected_week:
                        week_result = pred
                    else:
                        result_current, _ = augment_missing_summaries(published_current, prior, results_schedule, result_week)
                        week_result = predict_all_games(result_current, prior, results_schedule, result_week)
                        if not week_result.empty:
                            result_games = results_schedule[results_schedule["week"] == result_week]
                            week_result = attach_results(week_result, result_games)
                    if week_result.empty:
                        performance_errors.append(str(result_week))
                        continue
                    performance_frames.append(week_result)

                    # Value Pick history intentionally starts in Week 3. Weeks 1-2
                    # do not have enough current-season information for the tier structure.
                    if result_week < 3:
                        continue
                    if result_week == selected_week:
                        value_performance_frames.append(week_result)
                        continue

                    result_games = results_schedule[results_schedule["week"] == result_week]
                    result_dates = pd.to_datetime(
                        result_games.get("start_date", pd.Series(dtype=str)),
                        errors="coerce", utc=True,
                    ).dropna()
                    if result_dates.empty:
                        value_performance_errors.append(str(result_week))
                        continue
                    result_period = (
                        result_dates.min().strftime("%Y%m%d")
                        + "-"
                        + result_dates.max().strftime("%Y%m%d")
                    )
                    try:
                        result_quotes = download_market_odds(
                            result_period, schedule_event_ids(result_games)
                        )["quotes"]
                    except Exception:
                        value_performance_errors.append(str(result_week))
                        continue

                    week_value = add_betting_value(
                        attach_odds(week_result, result_games, result_quotes)
                    )
                    historical_weather = {}
                    try:
                        historical_profiles = build_waterfall_profiles(
                            results_schedule, waterfall_boxes, result_week
                        )
                        historical_weather_ids = weather_tier_candidate_ids(
                            week_value, results_schedule, historical_profiles
                        )
                        if historical_weather_ids:
                            historical_weather = value_weather_context(
                                results_schedule, result_week, tuple(historical_weather_ids)
                            )
                    except Exception:
                        historical_weather = {}

                    week_value = add_waterfall_value(
                        week_value,
                        results_schedule,
                        waterfall_boxes,
                        result_week,
                        weather_checks=historical_weather,
                        published_summary=published_current,
                    )
                    value_performance_frames.append(week_value)
                except Exception:
                    performance_errors.append(str(result_week))
                    if result_week >= 3:
                        value_performance_errors.append(str(result_week))

    st.caption(f"Historical reconstruction with model {MODEL_VERSION}, using snapshots from before each game week. These are recalculated picks, not an immutable record of predictions saved before kickoff. Revised source data or model updates can change historical results.")
    if performance_errors:
        st.warning("Partial model results: predictions could not be calculated for week(s) " + ", ".join(sorted(set(performance_errors), key=int)) + ". Those weeks are excluded.")

    if performance_frames:
        performance_detail = pd.concat(performance_frames, ignore_index=True)
        performance_summary = confidence_performance(performance_detail)
        total_graded = int(performance_summary["Graded"].sum())
        total_wins = int(performance_summary["Wins"].sum())
        r1, r2, r3 = st.columns(3)
        r1.metric("Graded picks", total_graded)
        r2.metric("Wins – losses", f"{total_wins} – {total_graded - total_wins}")
        r3.metric("Winner accuracy", f"{total_wins / total_graded:.1%}" if total_graded else "—")
        display_summary = performance_summary.copy()
        for column in ["Accuracy", "Average model confidence"]:
            display_summary[column] = display_summary[column].map(lambda v: f"{v:.1%}" if pd.notna(v) else "—")
        st.dataframe(display_summary, hide_index=True, use_container_width=True)
        st.caption("Average model confidence uses the same graded picks as accuracy. Very high is shown separately from High. Pending games, missing final scores, and ties do not count as wins or losses. Small samples can swing sharply.")
        if not total_graded:
            st.info("No final, decisive games to grade in this period yet.")
        with st.expander("See individual model results"):
            detail_columns = [c for c in ["Week", "Away Team", "Home Team", "Predicted Winner", "Confidence", "Status", "Actual Winner", "Pick Result", "Final Score"] if c in performance_detail]
            st.dataframe(performance_detail[detail_columns], hide_index=True, use_container_width=True)
        st.download_button(
            "Download confidence results · CSV",
            performance_summary.to_csv(index=False).encode(),
            file_name=f"cfb_{season}_{selected_week if performance_scope == 'Selected week' else 'season'}_confidence_results.csv",
            mime="text/csv",
            key="confidence_results_download",
        )
    else:
        st.info("No completed-game predictions are available for this period yet.")

    st.divider()
    st.subheader("Value Pick results")
    st.caption("Value Pick records use the current official tier rules and begin with Week 3. Weeks 1 and 2 are excluded because there was not enough current-season data for the tier structure.")
    if value_performance_errors:
        st.warning(
            "Partial Value Pick history: market/tier reconstruction could not be completed for week(s) "
            + ", ".join(sorted(set(value_performance_errors), key=int))
            + ". Those weeks are excluded from the Value Pick record."
        )

    if value_performance_frames:
        value_detail = pd.concat(value_performance_frames, ignore_index=True)
        value_summary = value_pick_performance(value_detail)
        if not value_summary.empty:
            overall = value_summary.iloc[0]
            overall_wins = int(overall["Wins"])
            overall_losses = int(overall["Losses"])
            overall_pushes = int(overall["Pushes"])
            decisive = overall_wins + overall_losses
            v1, v2, v3 = st.columns(3)
            v1.metric("Graded value picks", int(overall["Graded"]))
            record_text = f"{overall_wins} – {overall_losses}"
            if overall_pushes:
                record_text += f" – {overall_pushes} push" + ("es" if overall_pushes != 1 else "")
            v2.metric("Value Pick record", record_text)
            v3.metric("Value Pick win rate", f"{overall_wins / decisive:.1%}" if decisive else "—")

            display_value = value_summary.copy()
            display_value["Win rate"] = display_value["Win rate"].map(
                lambda v: f"{v:.1%}" if pd.notna(v) else "—"
            )
            st.dataframe(display_value, hide_index=True, use_container_width=True)
            st.caption("Win rate excludes pushes and not-graded selections from the denominator. Tier 1 and Tier 2 are graded ATS; Tiers 3–5 are graded straight up.")

            with st.expander("See individual Value Pick results"):
                value_rows = value_detail[
                    pd.to_numeric(value_detail.get("Week"), errors="coerce").ge(3)
                    & value_detail.get("Value Selected", pd.Series(False, index=value_detail.index)).fillna(False).astype(bool)
                ].copy()
                value_columns = [
                    c for c in [
                        "Week", "Away Team", "Home Team", "Value Tier", "Value Pick",
                        "Value Market", "Value Line", "Value Result", "Final Score",
                    ] if c in value_rows
                ]
                st.dataframe(value_rows[value_columns], hide_index=True, use_container_width=True)

            st.download_button(
                "Download Value Pick results · CSV",
                value_detail[
                    pd.to_numeric(value_detail.get("Week"), errors="coerce").ge(3)
                    & value_detail.get("Value Selected", pd.Series(False, index=value_detail.index)).fillna(False).astype(bool)
                ].to_csv(index=False).encode(),
                file_name=f"cfb_{season}_{selected_week if performance_scope == 'Selected week' else 'season'}_value_pick_results.csv",
                mime="text/csv",
                key="value_results_download",
            )
        else:
            st.info("No Value Picks from Week 3 onward are available for this period.")
    else:
        st.info("No Value Pick history is available for this period. Value Pick tracking begins in Week 3.")


with scenario_tab:
    tour_at("scenario")
    st.subheader(f"Live what-if · Week {selected_week}")
    st.caption("Choose any season and week above. Payouts use the latest fetched prices and update when you refresh feeds. These are hypothetical picks, not placed bets or locked-in odds.")
    if st.toggle("Open live calculator", key="live_calc_enabled"):
        live_pool = pred[pred["Bet Line"].map(format_moneyline).ne("Unavailable")].copy()
        if live_pool.empty:
            st.info("No published moneylines for this week. Try another week or refresh the feeds.")
        else:
            live_pool["Selection"] = live_pool.apply(lambda r: f"{r['Away Team']} at {r['Home Team']} — pick {r['Predicted Winner']}", axis=1)
            live_choices = st.multiselect("Choose picks", live_pool["Selection"].tolist(), key=f"live_picks_{season}_{selected_week}")
            amount = st.number_input("Default stake per pick ($)", min_value=0.0, max_value=100000.0, value=10.0, step=1.0, key="live_default_stake")
            selected_live = live_pool[live_pool["Selection"].isin(live_choices)]
            if not selected_live.empty:
                stake_table = selected_live[["Selection"]].copy()
                stake_table["Stake"] = amount
                edited = st.data_editor(stake_table, hide_index=True, disabled=["Selection"], key=f"live_stakes_{season}_{selected_week}_{amount}",
                                       column_config={"Stake": st.column_config.NumberColumn("Stake ($)", min_value=0.0, max_value=100000.0, step=1.0, required=True)})
                stake_by_pick = dict(zip(edited["Selection"], edited["Stake"]))
                live_rows = []
                for _, pick in selected_live.iterrows():
                    stake = stake_by_pick.get(pick["Selection"], amount)
                    if pd.isna(stake):
                        stake = 0.0
                    outcomes = payout_outcomes(stake, pick["Bet Line"])
                    if outcomes is None:
                        continue
                    actual_return, actual_profit = None, None
                    status = str(pick["Status"])
                    if status == "Final":
                        if pick["Actual Winner"] == "Tie":
                            actual_return, actual_profit = outcomes["Stake"], 0.0
                        elif pick["Actual Winner"] == pick["Predicted Winner"]:
                            actual_return, actual_profit = outcomes["Return if win"], outcomes["Profit if win"]
                        else:
                            actual_return, actual_profit = 0.0, outcomes["Loss if lose"]
                    live_rows.append({"Pick": pick["Predicted Winner"], "Matchup": pick["Selection"],
                                      "Moneyline": pick["Bet Line"], "Sportsbook": pick["ML Source"],
                                      "Line type": pick["Odds Type"], "Status": status, **outcomes,
                                      "Settled return": actual_return, "Settled profit": actual_profit})
                live_detail = pd.DataFrame(live_rows)
                settled_live = live_detail[live_detail["Status"].eq("Final")]
                pending_live = live_detail[~live_detail["Status"].eq("Final")]
                st.dataframe(live_detail, hide_index=True, use_container_width=True,
                             column_config={col: st.column_config.NumberColumn(col, format="$%.2f") for col in
                                            ["Stake", "Return if win", "Profit if win", "Loss if lose", "Settled return", "Settled profit"]})
                l1, l2, l3 = st.columns(3)
                l1.metric("Total selected stakes", f"${live_detail['Stake'].sum():,.2f}")
                l2.metric("Settled net profit", f"${settled_live['Settled profit'].sum():+,.2f}")
                l3.metric("Unsettled stakes", f"${pending_live['Stake'].sum():,.2f}")
                if not pending_live.empty:
                    st.write(f"If all unsettled picks win: ${pending_live['Return if win'].sum():,.2f} returned, including stakes; ${pending_live['Profit if win'].sum():+,.2f} profit.")
                    st.write(f"If all unsettled picks lose: ${pending_live['Stake'].sum():,.2f} lost.")
                st.caption("Final games use archived odds. Unsettled games use available feed prices, which may be delayed or unavailable at the sportsbook. Pending outcomes are hypothetical; ties refund stakes.")
                st.download_button("Download live scenario", live_detail.to_csv(index=False).encode(), file_name=f"cfb_{season}_week_{selected_week}_live_scenario.csv", mime="text/csv")
            else:
                st.info("Select one or more picks to calculate potential returns.")
    st.divider()
    st.subheader("What if you bet each pick?")
    st.caption("Simulate flat stakes by confidence tier. This uses all matchups in the scenario weeks, regardless of the search and card filters above.")
    if st.toggle("Calculate betting scenario", value=False):
        selected_scenario_weeks = st.multiselect("Scenario weeks", weeks, default=[selected_week])
        preset = st.selectbox("Quick setup", ["Original stakes", "$10 per pick", "$10 on value picks only", "Custom stakes"])
        scenario_mode = "Best betting opportunities" if preset == "$10 on value picks only" else "Confidence tiers"
        if preset == "Custom stakes":
            scenario_mode = st.radio("Scenario strategy", ["Confidence tiers", "Best betting opportunities"], horizontal=True)
        default_amounts = [10.0] * 4 if preset == "$10 per pick" else [10.0, 5.0, 2.5, 1.0]
        stake_columns = st.columns(4)
        stakes = {}
        if scenario_mode == "Confidence tiers":
            for column, tier, amount in zip(stake_columns, ["High", "Moderate", "Lean", "Toss-up"], default_amounts):
                with column:
                    stakes[tier] = st.number_input(f"{tier} stake ($)", min_value=0.0, value=amount, step=.5, format="%.2f", key=f"scenario_{preset}_{tier}")
            st.caption("High includes Very High: 80%+ · Moderate: 70–80% · Lean: 60–70% · Toss-up: under 60%.")
        else:
            with stake_columns[0]:
                opportunity_stake = st.number_input("Opportunity stake ($)", min_value=0.0, value=10.0, step=.5, format="%.2f")
            stakes = {tier: opportunity_stake for tier in ["High", "Moderate", "Lean", "Toss-up"]}
            st.caption("Uses the waterfall selections and their available market prices, even when the selected team differs from the core model. Equal stake per selection.")
        st.caption("See potential profit if pending picks win, plus actual results for settled bets. Total returned includes your original stake.")
        with st.expander("How this scenario is calculated"):
            st.write("Historical simulation using recalculated pregame-week predictions and archived prices, not a record of bets placed before kickoff. Missing moneylines are excluded; pending games are not settled. No parlays or reinvestment. Ties refund the stake; profit is rounded to cents per bet.")
        if selected_scenario_weeks:
            try:
                scenario_frames = []
                with st.spinner("Calculating your scenario..."):
                    for scenario_week in sorted(selected_scenario_weeks):
                        scenario_games = schedule[schedule["week"] == scenario_week]
                        scenario_current, _ = augment_missing_summaries(published_current, prior, schedule, scenario_week)
                        week_predictions = predict_all_games(scenario_current, prior, schedule, scenario_week)
                        if week_predictions.empty:
                            continue
                        week_predictions = attach_results(week_predictions, scenario_games)
                        scenario_dates = pd.to_datetime(scenario_games.get("start_date", pd.Series(dtype=str)), errors="coerce", utc=True).dropna()
                        quotes = {}
                        if not scenario_dates.empty:
                            period = scenario_dates.min().strftime("%Y%m%d") + "-" + scenario_dates.max().strftime("%Y%m%d")
                            try:
                                quotes = download_market_odds(period, schedule_event_ids(scenario_games))["quotes"]
                            except Exception:
                                st.warning(f"Week {scenario_week} odds could not be loaded; those bets are excluded.")
                        week_predictions = add_betting_value(attach_odds(week_predictions, scenario_games, quotes))
                        if scenario_mode == "Best betting opportunities":
                            week_predictions = add_waterfall_value(week_predictions, schedule, waterfall_boxes, scenario_week, published_summary=published_current)
                            week_predictions = waterfall_scenario_rows(week_predictions)
                        if not week_predictions.empty:
                            scenario_frames.append(simulate_stakes(week_predictions, stakes))
                if scenario_frames:
                    detail = pd.concat(scenario_frames, ignore_index=True)
                    settled = detail[detail["Scenario Status"] == "Settled"]
                    total_stake = settled["Stake"].sum()
                    total_return = settled["Returned"].sum()
                    total_profit = settled["Net Profit"].sum()
                    pending = detail[detail["Scenario Status"].eq("Pending final result")]
                    if not pending.empty:
                        st.markdown("### If the pending predicted winners win")
                        p1, p2, p3 = st.columns(3)
                        p1.metric("Pending stakes", f"${pending['Planned Stake'].sum():,.2f}")
                        p2.metric("Total payout if all win", f"${pending['Return if pick wins'].sum():,.2f}")
                        p3.metric("Net profit if all win", f"${pending['Profit if pick wins'].sum():+,.2f}")
                        st.write(f"If all pending picks lose: ${pending['Planned Stake'].sum():,.2f} lost.")
                        st.caption("Conditional outcomes using available sportsbook prices, not probability-weighted forecasts. Missing lines and zero stakes are excluded. Each pick is a separate bet.")
                        pending_view = pending[["Week", "Bet", "Market", "Odds", "Sportsbook", "Planned Stake", "Return if pick wins", "Profit if pick wins", "Loss if pick loses"]]
                        st.dataframe(pending_view, hide_index=True, use_container_width=True,
                                     column_config={col: st.column_config.NumberColumn(col, format="$%.2f") for col in ["Planned Stake", "Return if pick wins", "Profit if pick wins", "Loss if pick loses"]})
                        if not settled.empty:
                            st.write(f"Combined scenario net profit if pending picks all win: ${total_profit + pending['Profit if pick wins'].sum():+,.2f}; if all lose: ${total_profit - pending['Planned Stake'].sum():+,.2f}.")
                    st.markdown("### Settled results")
                    if settled.empty:
                        st.caption("No bets have settled yet. The figures below are actual results only; potential returns are shown above.")
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Total staked · priced, settled bets", f"${total_stake:,.2f}")
                    m2.metric("Total returned · includes stakes", f"${total_return:,.2f}")
                    m3.metric("Net profit / loss", f"${total_profit:+,.2f}")
                    if total_stake:
                        st.caption(f"ROI: {total_profit / total_stake:.1%} · {len(settled)} settled bets · {int(settled['Won'].sum())} wins / {int(settled['Lost'].sum())} losses")
                    skipped = detail[~detail["Scenario Status"].isin(["Settled", "Pending final result"])]
                    if not skipped.empty:
                        st.warning(f"{len(skipped)} picks excluded, representing ${skipped['Planned Stake'].sum():,.2f} in additional planned stakes. The displayed profit is not the exact outcome of betting every game.")
                    money_columns = {name: st.column_config.NumberColumn(name, format="$%.2f") for name in ["Staked", "Returned", "Net Profit"]}
                    for grouping in ["Week", "Tier"]:
                        st.markdown(f"**Results by {grouping.lower()}**")
                        summary = summarize_scenario(detail, grouping)
                        summary["ROI"] = summary["ROI"].map(lambda value: f"{value:.1%}" if pd.notna(value) else "—")
                        st.dataframe(summary, hide_index=True, use_container_width=True, column_config=money_columns)
                    with st.expander("Every simulated bet"):
                        view = detail.drop(columns=["Won", "Lost"]).copy()
                        view["Confidence"] = view["Confidence"].map(lambda value: f"{value:.1%}")
                        st.dataframe(view, hide_index=True, use_container_width=True)
                    st.download_button("Download scenario · CSV", detail.to_csv(index=False).encode(), file_name=f"cfb_{season}_betting_scenario.csv", mime="text/csv")
                else:
                    st.info("No matchups found for these weeks.")
            except Exception as exc:
                st.error(f"Could not calculate this scenario: {exc}")
        else:
            st.info("Choose at least one week to calculate a scenario.")

with parlay_tab:
    tour_at("parlay")
    st.subheader(f"Parlay finder · Week {selected_week}")
    st.caption("No AI subscription or paid API. Searches model picks with future kickoffs and available moneylines. Finished games and games already started are excluded.")
    st.caption("Payouts are estimates from multiplying individual moneylines, not sportsbook parlay quotes. Joint win probabilities assume independent outcomes. Each combination uses one sportsbook and distinct teams.")
    parlay_stake = st.number_input("Total parlay stake ($)", min_value=0.0, max_value=100000.0, value=10.0, step=1.0)

    featured_parlay = christians_parlay(
        pred, games, pd.Timestamp.now(tz="UTC"), stake=parlay_stake
    )
    if featured_parlay:
        with st.container(border=True, key=f"christians_parlay_{season}_{selected_week}"):
            st.markdown(
                '<div class="christians-parlay-kicker">🏈 Featured weekly parlay</div>'
                '<div class="christians-parlay-title">Christian’s Parlay</div>'
                + f'<div class="christians-parlay-formula">{escape(featured_parlay["formula"])} · '
                + f'{escape(featured_parlay["sportsbook"])}</div>',
                unsafe_allow_html=True,
            )
            for leg in featured_parlay["legs"]:
                st.markdown(
                    '<div class="christians-parlay-leg">'
                    + f'<div class="christians-parlay-tier">Tier {leg["stage"]}</div>'
                    + f'<strong>{escape(leg["bet"])}</strong><br>'
                    + f'<span>{escape(leg["away"])} at {escape(leg["home"])} · '
                    + f'price {escape(leg["price"])}</span>'
                    + '</div>',
                    unsafe_allow_html=True,
                )
            cp1, cp2, cp3 = st.columns(3)
            cp1.metric("Stake", f"${featured_parlay['stake']:,.2f}")
            cp2.metric("Return if all win", f"${featured_parlay['return']:,.2f}")
            cp3.metric("Profit if all win", f"${featured_parlay['profit']:+,.2f}")
            st.caption(
                f"If any leg loses: ${abs(featured_parlay['loss']):,.2f} lost. "
                "Uses four distinct current Value Pick games and DraftKings prices. "
                "Payout is an estimate; the sportsbook's live parlay quote can differ."
            )
    else:
        st.info(
            "Christian’s Parlay is unavailable this week because the current Value Picks "
            "do not satisfy the 4-leg formula with four distinct future games and usable DraftKings prices."
        )

    st.markdown("#### Build another parlay")
    legs = st.selectbox("Number of legs", [2, 3, 4, 5], index=1)
    goal = st.selectbox("Rank by", ["Highest win probability", "Highest payout", "Highest estimated value"])
    min_conf = st.slider("Minimum model confidence per leg (%)", 50, 95, 60, 5)
    data_rule = st.selectbox("Parlay team data", ["Any available data", "Published pregame summaries for both teams", "Exclude prior-data-only teams"])
    pool = future_priced_picks(pred, games, pd.Timestamp.now(tz="UTC"))
    pool = pool[pool["Confidence"] >= min_conf / 100]
    if data_rule != "Any available data":
        allowed = []
        for _, pick in pool.iterrows():
            published_both, estimated, prior_only = quality_by_match.get((pick["Home Team"], pick["Away Team"]), (False, False, True))
            allowed.append(published_both if data_rule == "Published pregame summaries for both teams" else not prior_only)
        pool = pool.loc[pd.Series(allowed, index=pool.index, dtype=bool)]
    books = sorted(pool["ML Source"].unique().tolist())
    book = st.selectbox("Sportsbook", ["Any single sportsbook"] + books)
    if book != "Any single sportsbook":
        pool = pool[pool["ML Source"].eq(book)]
    pool = pool.copy()
    pool["Decimal odds"] = pool["Bet Line"].map(lambda line: payout_outcomes(100, line)["Return if win"] / 100)
    sort_column = {"Highest win probability": "Confidence", "Highest payout": "Decimal odds", "Highest estimated value": "Expected Value"}[goal]
    total_candidates = len(pool)
    pool = pool.sort_values(sort_column, ascending=False).head(24)
    st.caption(f"Searching the top {len(pool)} of {total_candidates} eligible model picks by your ranking. All valid {legs}-leg combinations within this pool are compared; results are not a market-wide optimum.")
    if len(pool) < legs:
        st.info("Not enough eligible picks. Try another week, fewer legs, or broader filters.")
    else:
        results = rank_parlays(pool, legs, parlay_stake, goal)
        if not results:
            st.info("No combinations meet the one-sportsbook and distinct-team requirements.")
        for number, result in enumerate(results, 1):
            with st.container(border=True):
                st.markdown(f"**Option {number} · {result['legs'][0]['ML Source']}**")
                for leg in result["legs"]:
                    st.write(f"{leg['Predicted Winner']} ({leg['Bet Line']}) · {leg['Away Team']} at {leg['Home Team']} · model confidence {leg['Confidence']:.1%}")
                p1, p2, p3 = st.columns(3)
                p1.metric("Estimated win chance", f"{result['probability']:.1%}")
                p2.metric("Return if all win", f"${result['return']:,.2f}")
                p3.metric("Profit if all win", f"${result['profit']:,.2f}")
                st.caption(f"If any leg loses: ${abs(result['loss']):,.2f} lost. Total returned includes the stake. Ties/voids can change the payout under sportsbook rules.")
                st.write(f"Ranked by {goal.lower()} within the displayed search pool. Model-estimated profit per $1 staked: {result['ev']:+.2f}.")
                if result["ev"] < 0:
                    st.caption("The model estimates a negative expected return for this combination.")

with tracker_tab:
    tour_at("tracker")
    st.subheader("My bets")
    st.caption("Choose the season and week above to record a game. Final results update when the selected season schedule refreshes. Open older seasons to refresh their tracked results.")
    show_bet_tracker(overlay_live_scores(schedule, live_snapshot["games"]), pred, season, selected_week)

with about_tab:
    st.markdown("### Read your picks")
    st.write("DraftKings moneylines come from ESPN’s published odds feed, with other published sportsbooks used as a labeled fallback when needed. +150 means $100 would profit $150; −150 means risking $150 to profit $100. These prices are separate from the model’s win probabilities and do not change its picks.")
    st.write("Lines can move or be suspended. DraftKings is preferred, with labeled sportsbook fallbacks when available. Opening lines are not substituted for current prices. Completed-game moneylines come from archived game summaries and are labeled archived.")
    st.write("Each card shows both teams’ win probabilities and the predicted winner. A 70% confidence means an estimated 7 wins out of 10 similar matchups—not a guaranteed result.")
    st.markdown("**Confidence guide** · Very high: 90%+ · High: 80–90% · Moderate: 70–80% · Lean: 60–70% · Toss-up: below 60%.")
    st.write("Away-team picks may carry a venue-risk note. Use that as additional context when comparing games.")
    with st.expander("Model and data details"):
        st.write(f"Model {MODEL_VERSION}: 35% offense, 35% defense, 20% venue performance, and 10% strength of schedule.")
        st.write("Preseason strength combines 75% Elo and 25% prior-season efficiency. Current-season statistics gain weight as the season progresses. Only snapshots from before the selected week are used.")
        st.write("V1.5 adds a season-aware conference calibration for regular-season Power-versus-Group FBS matchups. It was fitted on 2022–23 and evaluated on 2024–25. Same-group games, independents, FCS games and postseason games receive no conference adjustment. Missing conference information also skips the adjustment.")
        st.caption("The adjustment improved historical probability scores but did not improve winner accuracy in every season. It does not establish better betting returns. The realigned 2026 Group of Six is a prospective application; historical scenarios are recalculated using the current model.")
        st.caption(f"Loaded {season}: {len(current):,} team-week rows; {season - 1}: {len(prior):,} rows. Source: SportsDataverse / cfbfastR.")

st.caption(f"Saturday Forecast · {MODEL_VERSION} · Estimates, not guarantees.")

watch_results(season, original_schedule if mode == "Automatic download" else None, date_range, odds_snapshot["quotes"], schedule_event_ids(games), live_snapshot["games"])




