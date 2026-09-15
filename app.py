from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from html import escape
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import math
from itertools import combinations
from heapq import nlargest
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlencode
from urllib.request import urlopen
from io import BytesIO
import base64
import pandas as pd
import numpy as np
import streamlit as st
from model import MODEL_VERSION, COMPONENT_SPEC, predict_week

st.set_page_config(page_title="College Football Predictor", page_icon="assets/cfb_icon.svg", layout="wide", initial_sidebar_state="collapsed")

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
    outcomes["Status"] = "Awaiting final"
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
    result = predictions.merge(outcomes[keys + ["Status", "Actual Winner", "Final Score"]], on=keys, how="left", validate="one_to_one")
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


def parse_draftkings(payload):
    """Return every sportsbook's current moneyline for each event.

    DraftKings is preferred in the UI. Other providers are retained as a
    clearly labeled fallback when DraftKings is unavailable or suspended.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise ValueError("Invalid odds response")
    quotes = {}
    for event in payload["events"]:
        event_quotes = {}
        for competition in event.get("competitions", []):
            sides = {c.get("homeAway"): str(c.get("team", {}).get("id", "")) for c in competition.get("competitors", [])}
            completed = bool(competition.get("status", {}).get("type", {}).get("completed", False))
            for odds in competition.get("odds", []):
                provider_name = str(odds.get("provider", {}).get("name", "")).strip()
                if not provider_name:
                    continue
                prices = {}
                for side in ("home", "away"):
                    market = odds.get("moneyline", {}).get(side, {})
                    value = (market.get("close") or {}).get("odds") if "close" in market else odds.get(side + "TeamOdds", {}).get("moneyLine")
                    prices[side] = format_moneyline(value)
                if prices["home"] == "Unavailable" and prices["away"] == "Unavailable":
                    continue
                event_quotes[provider_name] = {
                    "home_id": sides.get("home", ""), "away_id": sides.get("away", ""),
                    "home": prices["home"], "away": prices["away"], "completed": completed,
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
def download_archived_event(event_id):
    if not str(event_id).isdigit():
        return {}
    url = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event=" + str(event_id)
    with urlopen(url, timeout=15) as response:
        return parse_archived_summary(json.load(response), event_id)


@st.cache_data(ttl=300, show_spinner=False)
def download_market_odds(date_range):
    # This versioned function replaces the previous single-provider cache.
    query = urlencode({"dates": date_range, "groups": 80, "limit": 1000})
    url = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?" + query
    with urlopen(url, timeout=20) as response:
        payload = json.load(response)
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
    return {"quotes": quotes, "retrieved": datetime.now(ZoneInfo("America/Chicago")).strftime("%b %d, %I:%M %p %Z")}


def attach_odds(predictions, games, quotes):
    result = predictions.copy()
    result["DK Away ML"] = "Unavailable"
    result["DK Home ML"] = "Unavailable"
    result["Away ML"] = "Unavailable"
    result["Home ML"] = "Unavailable"
    result["ML Source"] = "Unavailable"
    result["Odds Type"] = "Not offered / unavailable"
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
        # Streamlit can briefly retain a cached response created by the older
        # single-provider parser during a deploy. Normalize that shape here.
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
            result.loc[index, "DK Away ML"] = dk["away"]
            result.loc[index, "DK Home ML"] = dk["home"]
        # Prefer DraftKings when either side is available. Otherwise choose the
        # first provider with a current price, preserving the source label.
        if dk and (dk["home"] != "Unavailable" or dk["away"] != "Unavailable"):
            selected_name, selected = dk_name, dk
        else:
            choices = [(name, quote) for name, quote in valid.items() if quote["home"] != "Unavailable" or quote["away"] != "Unavailable"]
            if not choices:
                continue
            selected_name, selected = choices[0]
        result.loc[index, "Away ML"] = selected["away"]
        result.loc[index, "Home ML"] = selected["home"]
        result.loc[index, "ML Source"] = selected_name
        result.loc[index, "Odds Type"] = "Archived line" if selected["completed"] or str(row["Status"]).startswith("Final") else "Latest available line"
    return result


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
    result["Bet Signal"] = "Pass"
    usable = result["Bet Line"].ne("Unavailable") & result["Expected Value"].notna()
    result.loc[usable & (result["Confidence"] >= .70) & (result["Model Edge"] >= .03) & (result["Expected Value"] > 0), "Bet Signal"] = "Strong value"
    result.loc[usable & (result["Bet Signal"] == "Pass") & (result["Confidence"] >= .60) & (result["Model Edge"] >= .02) & (result["Expected Value"] > 0), "Bet Signal"] = "Value"
    result.loc[~usable, "Bet Signal"] = "No line"
    return result


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


def team_logo_url(team_id):
    """ESPN's public college-football logo endpoint, keyed by team ID."""
    try:
        return f"https://a.espncdn.com/i/teamlogos/ncaa/500/{int(team_id)}.png"
    except (TypeError, ValueError, OverflowError):
        return ""


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
        line = pick["Home ML"] if pick["Predicted Side"] == "Home" else pick["Away ML"]
        valid_line = format_moneyline(line)
        reason = "Settled"
        returned = profit = None
        if stake <= 0:
            reason = "No bet · zero stake"
        elif pick["Status"] != "Final":
            reason = "Pending final result"
        elif valid_line == "Unavailable":
            reason = "Excluded · missing moneyline"
        else:
            odds = Decimal(valid_line)
            if pick["Actual Winner"] == "Tie":
                returned, profit = stake, Decimal("0")
            elif pick["Predicted Winner"] == pick["Actual Winner"]:
                profit = (stake * (odds / 100 if odds > 0 else 100 / abs(odds))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                returned = stake + profit
            else:
                returned, profit = Decimal("0"), -stake
        rows.append({
            "Week": int(pick["Week"]), "Away Team": pick["Away Team"], "Home Team": pick["Home Team"],
            "Pick": pick["Predicted Winner"], "Tier": tier, "Confidence": confidence,
            "Moneyline": valid_line, "Sportsbook": pick["ML Source"], "Actual Winner": pick["Actual Winner"],
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


@st.fragment(run_every="60s")
def watch_results(season, original, date_range, original_odds):
    if original is not None:
        try:
            if not download_schedule(season).equals(original):
                st.rerun()
        except Exception:
            st.caption("Results refresh is temporarily unavailable. Showing the last loaded data.")
    if date_range:
        try:
            if download_market_odds(date_range)["quotes"] != original_odds:
                st.rerun()
        except Exception:
            st.caption("Odds refresh is temporarily unavailable. Previously displayed lines may be stale.")
    st.caption("Results and odds check automatically while this page is open. Feeds refresh every 5 minutes and depend on source updates.")

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
</style>
<div class="hero"><div class="hero-brand"><div class="hero-mark">🏈</div><div><div class="eyebrow">Saturday scouting report · College football</div>
<h1>Your weekly game plan.</h1><p>Every matchup. A clear pick. Confidence at a glance.</p></div></div>
""", unsafe_allow_html=True)

now = datetime.now(timezone.utc)
year = now.year if now.month >= 7 else now.year - 1
season_col, week_col = st.columns([1, 2])
with season_col:
    season = int(st.number_input("Season", min_value=2001, max_value=now.year + 1, value=year))
with st.sidebar:
    st.header("Data settings")
    st.caption("Schedules and team statistics load automatically. No uploads needed.")
    if st.button("Refresh all data", use_container_width=True):
        download_schedule.clear()
        download_summary.clear()
        download_market_odds.clear()
        download_archived_event.clear()
    st.caption("Results and DraftKings odds refresh every 5 minutes; team summaries refresh hourly.")
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
    for col in ["home_division", "away_division"]:
        if col in schedule:
            schedule = schedule[schedule[col].astype(str).str.lower() == "fbs"]
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
    if not pred.empty:
        pred = attach_results(pred, games)
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
if date_range:
    try:
        odds_snapshot = download_market_odds(date_range)
    except Exception:
        st.info("DraftKings odds are temporarily unavailable. Predictions and results are still available.")
pred = add_betting_value(attach_odds(pred, games, odds_snapshot["quotes"]))

st.subheader(f"Week {selected_week} at a glance")
awaiting_count = int(pred["Status"].ne("Final").sum())
value_count = int(pred["Bet Signal"].isin(["Strong value", "Value"]).sum())
st.markdown(f"""<div class="overview">
<div class="stat"><strong>{awaiting_count}</strong><span>Awaiting final</span></div>
<div class="stat"><strong>{value_count}</strong><span>Model value picks</span></div>
<div class="stat"><strong>{len(pred)}</strong><span>Total matchups</span></div></div>""", unsafe_allow_html=True)
high_count = int((pred["Confidence"] >= .8).sum())
close_count = int((pred["Confidence"] < .6).sum())
graded = pred[pred["Pick Result"].isin(["Correct", "Incorrect"])]
correct_count = int(graded["Pick Result"].eq("Correct").sum())
accuracy = f"{correct_count / len(graded):.1%}" if len(graded) else "—"
st.markdown(f"""<div class="overview">
<div class="stat"><strong>{int(pred['Status'].eq('Final').sum())} / {len(pred)}</strong><span>Final scores available</span></div>
<div class="stat"><strong>{correct_count}–{len(graded) - correct_count}</strong><span>Correct – incorrect picks</span></div>
<div class="stat"><strong>{accuracy}</strong><span>Weekly accuracy · graded games</span></div></div>""", unsafe_allow_html=True)
schedule_time = original_schedule.attrs.get("fetched_at", "Uploaded CSV" if schedule_file is not None else "Unknown")
stats_time = published_current.attrs.get("fetched_at", "Uploaded CSV" if current_file is not None else "Unknown")
st.caption(f"Last fetched · Scores: {schedule_time} · Odds: {odds_snapshot['retrieved'] or 'Unavailable'} · Team stats: {stats_time}")
st.caption("Fetch times show when the app retrieved the feeds, not when the provider updated them. Scores and odds refresh every 5 minutes; team stats hourly.")
if st.button("Refresh all feeds now"):
    download_summary.clear()
    download_schedule.clear()
    download_market_odds.clear()
    download_archived_event.clear()
    st.rerun()
st.caption("Historical picks are recalculated from pregame-week statistics, not a saved record of picks issued before kickoff. Pending games and ties do not count toward accuracy.")
st.subheader(f"Week {selected_week} picks & results")
st.caption("DraftKings moneylines via ESPN, with another sportsbook shown when DraftKings is unavailable · American odds · Unavailable means no matching line is published. Verify the price in DraftKings before placing a bet.")
if odds_snapshot["retrieved"]:
    st.caption(f"Odds retrieved {odds_snapshot['retrieved']}. Completed-game moneylines are archived prices; they are not available to bet now.")
st.caption("Confidence is the model’s estimated chance that its pick wins. Even high-confidence picks can lose.")
value_picks = pred[pred["Bet Signal"].isin(["Strong value", "Value"])].sort_values(["Bet Signal", "Expected Value"], ascending=[True, False])
if not value_picks.empty:
    st.markdown("### Model value picks")
    st.caption("Weekly shortlist · includes all games regardless of the filters below.")
    st.caption("These picks combine the model’s win probability with the available moneyline. Model edge is the model confidence minus the market-implied probability; expected value estimates profit per $1 staked before sportsbook limits and line movement. Completed weeks use archived closing prices and include the actual result.")
    for _, value_pick in value_picks.head(12).iterrows():
        with st.container(border=True):
            st.markdown(f"**{value_pick['Predicted Winner']} · {value_pick['Bet Line']}**")
            st.caption(f"{value_pick['Away Team']} at {value_pick['Home Team']} · {value_pick['ML Source']} · {value_pick['Odds Type']}")
            v1, v2, v3 = st.columns(3)
            v1.metric("Model chance", f"{value_pick['Confidence']:.1%}")
            v2.metric("Break-even chance", f"{value_pick['Market Implied %']:.1%}")
            v3.metric("Model edge", f"{value_pick['Model Edge'] * 100:+.1f} pts")
            st.caption(f"{value_pick['Bet Signal']} · Estimated profit per $1: {value_pick['Expected Value']:+.2f}")
            if value_pick["Status"] == "Final":
                st.write(f"{value_pick['Pick Result']} · {value_pick['Final Score']}")
            else:
                st.caption("Awaiting final result")
    if pred["Status"].eq("Final").any():
        graded_value = value_picks[value_picks["Pick Result"].isin(["Correct", "Incorrect"])]
        if not graded_value.empty:
            wins = int(graded_value["Pick Result"].eq("Correct").sum())
            st.caption(f"Highlighted historical picks: {wins}–{len(graded_value) - wins} ({wins / len(graded_value):.1%} accuracy).")
else:
    st.info("No current game has both a published moneyline and enough model value to qualify as a highlighted opportunity.")
def reset_pick_filters():
    defaults = {"pick_query": "", "pick_level": "All confidence levels",
                "pick_order": "Highest confidence", "pick_status": "All games",
                "pick_odds": "All odds", "pick_quality": "All data",
                "pick_favorites_only": False}
    for key, value in defaults.items():
        st.session_state[key] = value


st.subheader("Explore matchups")
team_choices = sorted(set(schedule["home_team"]) | set(schedule["away_team"]))
favorite_choices = sorted(set(team_choices) | set(st.session_state.get("favorite_teams", [])))
favorites = st.multiselect("Favorite teams", favorite_choices, key="favorite_teams",
                           help="Saved during this app session. Choose teams, then turn on Favorites only.")
st.checkbox("Favorites only", key="pick_favorites_only")
st.button("Reset filters", on_click=reset_pick_filters,
          help="Resets matchup filters and keeps your favorite-team list.")
search_col, confidence_col, sort_col = st.columns([2, 1, 1])
with search_col:
    query = st.text_input("Find a team", placeholder="Search LSU, Texas, Ohio State…", key="pick_query")
with confidence_col:
    level = st.selectbox("Confidence", ["All confidence levels", "High · 80%+", "Moderate · 70–80%", "Lean · 60–70%", "Toss-up · under 60%"], key="pick_level")
with sort_col:
    order = st.selectbox("Sort by", ["Highest confidence", "Closest matchups", "Home team A–Z"], key="pick_order")
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
elif order == "Home team A–Z":
    filtered = filtered.sort_values("Home Team")
status_filter = st.radio("Game results", ["All games", "Final", "Awaiting final", "Correct picks", "Incorrect picks"], horizontal=True, key="pick_status")
if status_filter == "Final":
    filtered = filtered[filtered["Status"].eq("Final")]
elif status_filter == "Awaiting final":
    filtered = filtered[~filtered["Status"].eq("Final")]
elif status_filter in ["Correct picks", "Incorrect picks"]:
    filtered = filtered[filtered["Pick Result"].eq(status_filter.split()[0])]

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

cards_tab, table_tab, scenario_tab, parlay_tab, about_tab = st.tabs(["Game cards", "Compare picks", "What-if bets", "Parlay finder", "How it works"])
with cards_tab:
    if filtered.empty:
        st.info("No matchups match these filters. Clear your search or choose another confidence level.")
    else:
        cards = []
        for _, r in filtered.iterrows():
            badge_class = "badge close" if r["Confidence"] < .7 else "badge"
            risk = '<div class="risk-note">Away-team pick · ' + escape(str(r["Venue Risk"])) + ' venue risk</div>' if r["Venue Risk"] != "Normal" else ""
            venue = "Neutral site" if r["Neutral Site"] else "Away at home"
            outcome_class = "badge" if r["Pick Result"] == "Correct" else "badge incorrect" if r["Pick Result"] == "Incorrect" else "badge close"
            outcome = f'<div class="result-box"><span class="{outcome_class}">{escape(str(r["Pick Result"]))}</span><div class="result-score">{escape(str(r["Status"]))} · {escape(str(r["Final Score"]))}</div><div>Actual winner: <strong>{escape(str(r["Actual Winner"]))}</strong></div></div>'
            moneylines = f'<div class="odds-box"><div class="pick-label">Moneyline · {escape(str(r["ML Source"]))}</div><div class="odds-prices"><span>Away <strong>{escape(str(r["Away ML"]))}</strong></span><span>Home <strong>{escape(str(r["Home ML"]))}</strong></span></div><div class="venue-label" style="margin-top:8px">{escape(str(r["Odds Type"]))}</div></div>'
            game = games[(games["home_team"] == r["Home Team"]) & (games["away_team"] == r["Away Team"])]
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
            away_logo_html = f'<img class="team-logo" src="{away_logo}" alt="" />' if away_logo else ""
            home_logo_html = f'<img class="team-logo" src="{home_logo}" alt="" />' if home_logo else ""
            home_badge, away_badge = "<!--home-data-->", "<!--away-data-->"
            kickoff = "Kickoff time TBD"
            if len(game) == 1:
                date = pd.to_datetime(game.iloc[0].get("start_date"), errors="coerce", utc=True)
                if pd.notna(date):
                    kickoff = date.tz_convert("America/Chicago").strftime("%a, %b %d · %I:%M %p %Z")
            if r["Status"] != "Final":
                outcome = '<div class="result-box">' + escape(str(r["Status"])) + '</div>'
            cards.append(f"""<article class="pick-card">
<div class="card-top"><span>{venue}</span><span class="{badge_class}">{escape(str(r['Confidence Label']))}</span></div>
<div class="kickoff">{escape(kickoff)}</div>
<div class="team-line"><div class="team-name"><span class="venue-label">Away</span><span class="team-identity">{away_logo_html}{escape(str(r['Away Team']))}</span>{away_badge}</div><strong>{r['Away Win %']:.1%}</strong></div>
<div class="team-line"><div class="team-name"><span class="venue-label">Home</span><span class="team-identity">{home_logo_html}{escape(str(r['Home Team']))}</span>{home_badge}</div><strong>{r['Home Win %']:.1%}</strong></div>
<div class="pick-result"><div class="pick-label">Predicted winner</div><div class="pick-winner">{escape(str(r['Predicted Winner']))}</div>
<div class="conf-row"><span>Win confidence</span><strong>{r['Confidence']:.1%}</strong></div>
<div class="conf-track"><div class="conf-fill" style="width:{r['Confidence'] * 100:.1f}%"></div></div></div>{moneylines}{outcome}<details class="card-details"><summary>Prediction details</summary><p>Model {escape(str(r['Model Version']))} · {escape(venue)}. Confidence is an estimate, not a guaranteed result.</p>{risk}{missing_data_note}</details></article>""")
        for card_index, (_, pick) in enumerate(filtered.iterrows()):
            card = cards[card_index].replace('<article class="pick-card">', '').replace('</article>', '')
            header, rest = card.split("<!--away-data-->", 1)
            middle, footer = rest.split("<!--home-data-->", 1)
            # Close team wrappers before inserting Streamlit widgets.
            header += f"</div><strong>{pick['Away Win %']:.1%}</strong></div>"
            middle = middle.split("</div>", 2)[-1] + f"</div><strong>{pick['Home Win %']:.1%}</strong></div>"
            footer = footer.split("</div>", 2)[-1]
            matchup = games[(games["home_team"] == pick["Home Team"]) & (games["away_team"] == pick["Away Team"])]
            with st.container(border=True):
                st.markdown(header, unsafe_allow_html=True)
                for side, section in [("away", middle), ("home", footer)]:
                    tid = matchup.iloc[0][side + "_id"] if len(matchup) == 1 else None
                    label, note, metrics = team_data_details(tid, published_current, derived_team_data, selected_week)
                    with st.expander(f"{pick[side.title() + ' Team']} · {label}"):
                        st.caption(note)
                        for metric, value in metrics.items():
                            st.write(f"**{metric}:** {value}")
                    st.markdown(section, unsafe_allow_html=True)
with table_tab:
    show = filtered[["Away Team", "Home Team", "Predicted Winner", "Confidence", "Confidence Label", "Away Win %", "Home Win %", "DK Away ML", "DK Home ML", "Away ML", "Home ML", "ML Source", "Odds Type", "Status", "Actual Winner", "Final Score", "Pick Result", "Venue Risk"]].copy()
    for col in ["Confidence", "Away Win %", "Home Win %"]:
        show[col] = show[col].map(lambda value: f"{value:.1%}")
    st.dataframe(show, hide_index=True, use_container_width=True)
with scenario_tab:
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
            st.caption("Includes only picks labeled Strong value or Value: positive expected value, with the model edge thresholds shown above.")
        st.caption("Only priced, settled bets count toward profit. Total returned includes your original stake.")
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
                                quotes = download_market_odds(period)["quotes"]
                            except Exception:
                                st.warning(f"Week {scenario_week} odds could not be loaded; those bets are excluded.")
                        week_predictions = add_betting_value(attach_odds(week_predictions, scenario_games, quotes))
                        if scenario_mode == "Best betting opportunities":
                            week_predictions = week_predictions[week_predictions["Bet Signal"].isin(["Strong value", "Value"])]
                        if not week_predictions.empty:
                            scenario_frames.append(simulate_stakes(week_predictions, stakes))
                if scenario_frames:
                    detail = pd.concat(scenario_frames, ignore_index=True)
                    settled = detail[detail["Scenario Status"] == "Settled"]
                    total_stake = settled["Stake"].sum()
                    total_return = settled["Returned"].sum()
                    total_profit = settled["Net Profit"].sum()
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Total staked · priced, settled bets", f"${total_stake:,.2f}")
                    m2.metric("Total returned · includes stakes", f"${total_return:,.2f}")
                    m3.metric("Net profit / loss", f"${total_profit:+,.2f}")
                    if total_stake:
                        st.caption(f"ROI: {total_profit / total_stake:.1%} · {len(settled)} settled bets · {int(settled['Won'].sum())} wins / {int(settled['Lost'].sum())} losses")
                    skipped = detail[detail["Scenario Status"] != "Settled"]
                    if not skipped.empty:
                        st.warning(f"{len(skipped)} picks excluded or pending, representing ${skipped['Planned Stake'].sum():,.2f} in additional planned stakes. The displayed profit is not the exact outcome of betting every game.")
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
    st.subheader(f"Parlay finder · Week {selected_week}")
    st.caption("No AI subscription or paid API. Searches model picks with future kickoffs and available moneylines. Finished games and games already started are excluded.")
    st.caption("Payouts are estimates from multiplying individual moneylines, not sportsbook parlay quotes. Joint win probabilities assume independent outcomes. Each combination uses one sportsbook and distinct teams.")
    if st.toggle("Open parlay finder", key="parlay_enabled"):
        legs = st.selectbox("Number of legs", [2, 3, 4, 5], index=1)
        parlay_stake = st.number_input("Total parlay stake ($)", min_value=0.0, max_value=100000.0, value=10.0, step=1.0)
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
        st.caption(f"Loaded {season}: {len(current):,} team-week rows; {season - 1}: {len(prior):,} rows. Source: SportsDataverse / cfbfastR.")

st.download_button("Download these picks · CSV", filtered.to_csv(index=False).encode(), file_name=f"cfb_{season}_{MODEL_VERSION}_week_{selected_week}.csv", mime="text/csv", disabled=filtered.empty)
st.caption(f"College Football Predictor · {MODEL_VERSION} · Estimates, not guarantees.")

watch_results(season, original_schedule if mode == "Automatic download" else None, date_range, odds_snapshot["quotes"])
