from datetime import datetime, timezone
from urllib.request import urlopen
from io import BytesIO
import pandas as pd
import streamlit as st
from model import MODEL_VERSION, COMPONENT_SPEC, predict_week

st.set_page_config(page_title="College Football Predictor", page_icon="🏈", layout="wide")

@st.cache_data(ttl=3600)
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

st.title("🏈 College Football Predictor")
st.caption(f"Frozen production model: {MODEL_VERSION}")
with st.sidebar:
    st.header("Data")
    now = datetime.now(timezone.utc)
    year = now.year if now.month >= 7 else now.year - 1
    season = int(st.number_input("Season", min_value=2001, max_value=now.year + 1, value=year))
    mode = st.radio("Schedule source", ["Automatic download", "Upload CSV"])
    schedule_file = st.file_uploader("Schedule CSV", type="csv") if mode == "Upload CSV" else None
    if st.button("Refresh all data"):
        download_schedule.clear()
        download_summary.clear()
    st.caption("Schedules and team summaries download automatically and refresh hourly while using the app.")
    with st.expander("Optional CSV overrides"):
        current_file = st.file_uploader(f"{season} team summaries", type="csv")
        prior_file = st.file_uploader(f"{season - 1} team summaries", type="csv")
    st.divider()
    st.markdown("**V1.4 architecture**")
    st.write("35% offense · 35% defense · 20% venue · 10% SOS")
    st.write("Prior: 75% preseason Elo + 25% prior-season efficiency")

if mode == "Upload CSV" and schedule_file is None:
    st.info("Upload a schedule or select Automatic download.")
    st.stop()
try:
    schedule = pd.read_csv(schedule_file, low_memory=False) if schedule_file is not None else download_schedule(season)
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
selected_week = st.selectbox("Week", weeks, index=weeks.index(default_week))
with st.expander("Weekly matchups", expanded=True):
    games = schedule[schedule["week"] == selected_week]
    cols = [c for c in ["away_team", "home_team", "start_date", "completed"] if c in games]
    st.dataframe(games[cols], hide_index=True, use_container_width=True)
st.caption("Schedule: sportsdataverse/cfbfastR-data · Regular-season FBS vs. FBS games")

try:
    with st.spinner("Loading team statistics and generating predictions..."):
        current = read_summary(current_file, season)
        prior = read_summary(prior_file, season - 1)
except Exception as exc:
    st.error(f"Could not load team summaries: {exc}")
    st.info("Try Refresh all data. If the selected season is not published yet, choose an available season or supply CSV overrides.")
    st.stop()
st.caption(f"Team summaries loaded: {season} ({len(current):,} rows), {season - 1} ({len(prior):,} rows).")
eligible = current[current["through_week"] < selected_week]
if selected_week > 1:
    team_ids = set(games["home_id"]) | set(games["away_id"])
    missing_teams = team_ids - set(eligible["team_id"])
    if missing_teams:
        st.warning(f"{len(missing_teams)} teams have no published pregame statistics for this week; their predictions use the model's prior-data fallback.")
    if not eligible.empty and eligible["through_week"].max() < selected_week - 1:
        st.warning(f"Published statistics currently extend through week {int(eligible['through_week'].max())}. Predictions use the latest available pregame snapshot.")
try:
    pred = predict_week(current, prior, schedule, selected_week)
except Exception as e:
    st.error(str(e))
    st.stop()

tab1, tab2, tab3 = st.tabs(["Predictions", "Game Cards", "Model"])

with tab1:
    if pred.empty:
        st.warning("No games found for this week.")
    else:
        show = pred.copy()
        for c in ["Away Win %","Home Win %","Confidence"]:
            show[c] = show[c].map(lambda x: f"{x:.1%}")
        st.dataframe(
            show[[
                "Away Team","Home Team","Away Win %","Home Win %",
                "Predicted Winner","Confidence","Confidence Label","Venue Risk"
            ]],
            use_container_width=True,
            hide_index=True
        )
        st.download_button(
            "Download predictions",
            pred.to_csv(index=False).encode(),
            file_name=f"cfb_{MODEL_VERSION}_week_{selected_week}.csv",
            mime="text/csv"
        )

with tab2:
    for _, r in pred.iterrows():
        with st.container(border=True):
            st.subheader(f"{r['Away Team']} at {r['Home Team']}")
            c1, c2, c3 = st.columns(3)
            c1.metric("Projected winner", r["Predicted Winner"])
            c2.metric("Confidence", f"{r['Confidence']:.1%}")
            c3.metric("Venue risk", r["Venue Risk"])
            st.progress(float(r["Home Win %"]), text=f"{r['Home Team']} win probability: {r['Home Win %']:.1%}")
            st.caption(f"{r['Away Team']}: {r['Away Win %']:.1%} · {r['Home Team']}: {r['Home Win %']:.1%}")
            if r["Predicted Side"] == "Away" and r["Venue Risk"] != "Normal":
                st.warning("Road-team selection: historical V1.4 diagnostics show elevated contextual risk.")

with tab3:
    st.markdown("""
    ### V1.4 frozen model
    **Core weights**
    - 35% Offensive efficiency
    - 35% Defensive efficiency
    - 20% Team-specific venue performance
    - 10% Strength of schedule

    **Efficiency composite**
    - 40% EPA/PPA
    - 30% Success rate
    - 15% Explosiveness
    - 15% Red-zone success proxy

    **Prior strength**
    - 75% preseason Elo
    - 25% prior-season efficiency

    **Current-season transition**
    - W1 30%
    - W2 40%
    - W3 50%
    - W4 60%
    - W5 65%
    - W6 70%
    - W7 75%
    - W8 80%
    - W9 85%
    - W10+ 90%

    **2025 frozen benchmark**
    - 762 regular-season FBS-vs-FBS games
    - 73.1% straight-up accuracy
    - 0.185 Brier score

    Probabilities are estimates, not guarantees.
    """)

st.divider()
st.caption("Model versioning is frozen so future improvements can be tested as V1.5+ without silently changing V1.4.")

