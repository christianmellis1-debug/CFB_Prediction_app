
import pandas as pd
import streamlit as st

from model import MODEL_VERSION, predict_week

st.set_page_config(page_title="College Football Predictor", page_icon="🏈", layout="wide")

st.title("🏈 College Football Predictor")
st.caption(f"Frozen production model: {MODEL_VERSION}")

with st.sidebar:
    st.header("Upload data")
    current_file = st.file_uploader("Current-season team summaries", type="csv")
    prior_file = st.file_uploader("Prior-season team summaries", type="csv")
    schedule_file = st.file_uploader("Current-season schedule", type="csv")

    st.divider()
    st.markdown("**V1.4 architecture**")
    st.write("35% offense · 35% defense · 20% venue · 10% SOS")
    st.write("Prior: 75% preseason Elo + 25% prior-season efficiency")

if not (current_file and prior_file and schedule_file):
    st.info("Upload all three CSVs to generate weekly predictions.")
    st.markdown("""
    **Outputs**
    - Win probability for each team
    - Predicted winner
    - Confidence tier
    - Road-favorite venue risk
    - Downloadable prediction CSV
    """)
else:
    current = pd.read_csv(current_file, low_memory=False)
    prior = pd.read_csv(prior_file, low_memory=False)
    schedule = pd.read_csv(schedule_file, low_memory=False)

    weeks = sorted(pd.to_numeric(schedule["week"], errors="coerce").dropna().astype(int).unique())
    selected_week = st.selectbox("Week", weeks)

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
