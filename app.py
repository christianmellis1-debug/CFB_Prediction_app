from datetime import datetime, timezone
from html import escape
import json
import math
from urllib.parse import urlencode
from urllib.request import urlopen
from io import BytesIO
import pandas as pd
import streamlit as st
from model import MODEL_VERSION, COMPONENT_SPEC, predict_week

st.set_page_config(page_title="College Football Predictor", page_icon="🏈", layout="wide", initial_sidebar_state="collapsed")

@st.cache_data(ttl=300)
def download_schedule(season):
    url = f"https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main/schedules/csv/cfb_schedules_{season}.csv"
    with urlopen(url, timeout=30) as response:
        return pd.read_csv(BytesIO(response.read()), low_memory=False)

@st.cache_data(ttl=3600, show_spinner=False)
def download_summary(year):
    url = (
        "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"
        f"cfb_team_summaries_weekly/cfb_team_summaries_weekly_{year}.csv"
    )
    with urlopen(url, timeout=60) as response:
        return pd.read_csv(BytesIO(response.read()), low_memory=False)


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


@st.cache_data(ttl=300, show_spinner=False)
def download_odds(date_range):
    query = urlencode({"dates": date_range, "groups": 80, "limit": 1000})
    url = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?" + query
    with urlopen(url, timeout=20) as response:
        payload = json.load(response)
    return {"quotes": parse_draftkings(payload), "retrieved": datetime.now(timezone.utc).strftime("%b %d, %H:%M UTC")}


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
        valid = {}
        for provider, quote in event_quotes.items():
            if quote.get("home_id") == str(int(game.home_id)) and quote.get("away_id") == str(int(game.away_id)):
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
            if download_odds(date_range)["quotes"] != original_odds:
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
@media (max-width:1000px) {.pick-grid {grid-template-columns:repeat(2,minmax(0,1fr));}}
@media (max-width:600px) {.block-container {padding:4rem 1rem 2rem;}.hero {padding:25px 22px;border-radius:18px;}.pick-grid {grid-template-columns:1fr;}.overview {gap:8px;}.stat {padding:12px 10px;}.stat strong {font-size:23px;}.stat span {font-size:11px;}}
</style>
<div class="hero"><div class="eyebrow">Saturday scouting report · College football</div>
<h1>Your weekly game plan.</h1><p>Every matchup. A clear pick. Confidence at a glance.</p></div>
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
        download_odds.clear()
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
except Exception as exc:
    st.error(f"Could not load team summaries: {exc}")
    st.info("Try Refresh all data. If the selected season is not published yet, choose an available season or supply CSV overrides.")
    st.stop()

eligible = current[current["through_week"] < selected_week]
if selected_week > 1:
    team_ids = set(games["home_id"]) | set(games["away_id"])
    missing_teams = team_ids - set(eligible["team_id"])
    if missing_teams:
        st.warning(f"{len(missing_teams)} teams have no published pregame statistics for this week; their predictions use the model's prior-data fallback.")
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
        odds_snapshot = download_odds(date_range)
    except Exception:
        st.info("DraftKings odds are temporarily unavailable. Predictions and results are still available.")
pred = attach_odds(pred, games, odds_snapshot["quotes"])

high_count = int((pred["Confidence"] >= .8).sum())
close_count = int((pred["Confidence"] < .6).sum())
st.markdown(f"""<div class="overview">
<div class="stat"><strong>{len(pred)}</strong><span>Matchup predictions</span></div>
<div class="stat"><strong>{high_count}</strong><span>High confidence · 80%+</span></div>
<div class="stat"><strong>{close_count}</strong><span>Toss-ups · under 60%</span></div></div>""", unsafe_allow_html=True)
graded = pred[pred["Pick Result"].isin(["Correct", "Incorrect"])]
correct_count = int(graded["Pick Result"].eq("Correct").sum())
accuracy = f"{correct_count / len(graded):.1%}" if len(graded) else "—"
st.markdown(f"""<div class="overview">
<div class="stat"><strong>{int(pred['Status'].eq('Final').sum())} / {len(pred)}</strong><span>Final scores available</span></div>
<div class="stat"><strong>{correct_count}–{len(graded) - correct_count}</strong><span>Correct – incorrect picks</span></div>
<div class="stat"><strong>{accuracy}</strong><span>Weekly accuracy · graded games</span></div></div>""", unsafe_allow_html=True)
if st.button("Refresh scores & odds now"):
    download_schedule.clear()
    download_odds.clear()
    st.rerun()
st.caption("Historical picks are recalculated from pregame-week statistics, not a saved record of picks issued before kickoff. Pending games and ties do not count toward accuracy.")
st.subheader(f"Week {selected_week} picks & results")
st.caption("DraftKings moneylines via ESPN, with another sportsbook shown when DraftKings is unavailable · American odds · Unavailable means no matching line is published. Verify the price in DraftKings before placing a bet.")
if odds_snapshot["retrieved"]:
    st.caption(f"Odds retrieved {odds_snapshot['retrieved']}. Completed-game lines, if provided, are labeled archived.")
st.caption("Confidence is the model’s estimated chance that its pick wins. Even high-confidence picks can lose.")
search_col, confidence_col, sort_col = st.columns([2, 1, 1])
with search_col:
    query = st.text_input("Find a team", placeholder="Search LSU, Texas, Ohio State…")
with confidence_col:
    level = st.selectbox("Confidence", ["All confidence levels", "High · 80%+", "Moderate · 70–80%", "Lean · 60–70%", "Toss-up · under 60%"])
with sort_col:
    order = st.selectbox("Sort by", ["Highest confidence", "Closest matchups", "Home team A–Z"])
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
status_filter = st.radio("Game results", ["All games", "Final", "Awaiting final", "Correct picks", "Incorrect picks"], horizontal=True)
if status_filter == "Final":
    filtered = filtered[filtered["Status"].eq("Final")]
elif status_filter == "Awaiting final":
    filtered = filtered[~filtered["Status"].eq("Final")]
elif status_filter in ["Correct picks", "Incorrect picks"]:
    filtered = filtered[filtered["Pick Result"].eq(status_filter.split()[0])]

st.caption(f"Showing {len(filtered)} of {len(pred)} predictions · {season} regular season · FBS vs. FBS")

cards_tab, table_tab, about_tab = st.tabs(["Game cards", "Compare picks", "How it works"])
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
            cards.append(f"""<article class="pick-card">
<div class="card-top"><span>{venue}</span><span class="{badge_class}">{escape(str(r['Confidence Label']))}</span></div>
<div class="team-line"><span class="team-name"><span class="venue-label">Away</span>{escape(str(r['Away Team']))}</span><strong>{r['Away Win %']:.1%}</strong></div>
<div class="team-line"><span class="team-name"><span class="venue-label">Home</span>{escape(str(r['Home Team']))}</span><strong>{r['Home Win %']:.1%}</strong></div>
<div class="pick-result"><div class="pick-label">Predicted winner</div><div class="pick-winner">{escape(str(r['Predicted Winner']))}</div>
<div class="conf-row"><span>Win confidence</span><strong>{r['Confidence']:.1%}</strong></div>
<div class="conf-track"><div class="conf-fill" style="width:{r['Confidence'] * 100:.1f}%"></div></div></div>{moneylines}{outcome}{risk}</article>""")
        st.markdown('<div class="pick-grid">' + ''.join(cards) + '</div>', unsafe_allow_html=True)
with table_tab:
    show = filtered[["Away Team", "Home Team", "Predicted Winner", "Confidence", "Confidence Label", "Away Win %", "Home Win %", "DK Away ML", "DK Home ML", "Away ML", "Home ML", "ML Source", "Odds Type", "Status", "Actual Winner", "Final Score", "Pick Result", "Venue Risk"]].copy()
    for col in ["Confidence", "Away Win %", "Home Win %"]:
        show[col] = show[col].map(lambda value: f"{value:.1%}")
    st.dataframe(show, hide_index=True, use_container_width=True)
with about_tab:
    st.markdown("### Read your picks")
    st.write("DraftKings moneylines come from ESPN’s published odds feed, with other published sportsbooks used as a labeled fallback when needed. +150 means $100 would profit $150; −150 means risking $150 to profit $100. These prices are separate from the model’s win probabilities and do not change its picks.")
    st.write("Lines can move or be suspended. Unavailable prices are never filled with opening lines or another bookmaker’s odds. Historical lines are shown only when the feed supplies them.")
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
