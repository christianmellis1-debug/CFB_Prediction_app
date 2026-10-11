"""Research-only V1.5 component weight sensitivity with exact production feature math.

This script never updates production model files. Every game uses the latest
weekly advanced-stat profile from STRICTLY earlier weeks. 2024 selects a
candidate; 2025 and 2026 are described separately (both have been inspected
in prior projects and are not pristine unseen holdouts).
"""
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import json
import math
import numpy as np
import pandas as pd
from scipy.special import expit

from shadow_inputs import download_schedule, read_summary
from matchup_advantages import normalize_fbs_schedule
import model_v1_5 as model

OUT = Path("research/weight_sensitivity_2026_10_11/results.json")
ALPHA = model.CALIBRATION_SLOPE * 1.10
BASE = {"off": 0.35, "def": 0.35, "venue": 0.20, "sos": 0.10}

# Changes are predeclared to avoid finding a "winner" through a huge,
# opaque search over past seasons.
WEIGHTS = {
    "baseline": (.35, .35, .20, .10),
    "offense_40_defense_30": (.40, .30, .20, .10),
    "offense_45_defense_25": (.45, .25, .20, .10),
    "offense_50_defense_20": (.50, .20, .20, .10),
    "defense_40_offense_30": (.30, .40, .20, .10),
    "defense_45_offense_25": (.25, .45, .20, .10),
    "defense_50_offense_20": (.20, .50, .20, .10),
    "venue_10_efficiency_80": (.40, .40, .10, .10),
    "venue_05_efficiency_85": (.425, .425, .05, .10),
    "venue_00_efficiency_90": (.45, .45, .00, .10),
    "venue_30_efficiency_60": (.30, .30, .30, .10),
    "venue_40_efficiency_50": (.25, .25, .40, .10),
    "sos_20_venue_10": (.35, .35, .10, .20),
    "sos_20_offense_30": (.30, .30, .20, .20),
    "sos_00_efficiency_80": (.40, .40, .20, .00),
    "sos_15_venue_15": (.35, .35, .15, .15),
    "offense_40_defense_40_venue_15": (.40, .40, .15, .05),
    "defense_40_venue_15": (.35, .40, .15, .10),
    "offense_40_venue_15": (.40, .35, .15, .10),
    "defense_40_sos_05": (.35, .40, .20, .05),
    "offense_40_sos_05": (.40, .35, .20, .05),
}
assert all(abs(sum(w) - 1) < 1e-9 and min(w) >= 0 for w in WEIGHTS.values())


def games_for(year):
    s = download_schedule(year)
    s = s[s["season_type"].astype(str).str.lower().eq("regular")].copy()
    s = normalize_fbs_schedule(s)
    for col in ("week", "home_id", "away_id", "game_id", "home_points", "away_points"):
        s[col] = pd.to_numeric(s[col], errors="coerce")
    s = s.dropna(subset=["week", "home_id", "away_id"])
    s = s[s.week.ge(1)]
    for col in ("completed", "neutral_site"):
        s[col] = s[col].astype(str).str.lower().isin(["true", "t", "1", "1.0", "yes", "y"])
    s = s.sort_values("start_date", kind="stable")
    return s


def assemble_features(year):
    schedule = games_for(year)
    current, prior = read_summary(None, year), read_summary(None, year - 1)
    scores, weeks = model.build_weekly_scores(current)
    prior_vector = model.build_prior_profiles(prior, schedule)
    items = []
    for week in sorted(schedule.week.dropna().astype(int).unique()):
        if year == 2026 and week > 6:
            break
        histories_home, histories_away = model._completed_history(schedule, week)
        target = schedule[schedule.week.eq(week)]
        target = target[target.completed & target.home_points.notna() & target.away_points.notna()]
        for _, g in target.iterrows():
            if float(g.home_points) == float(g.away_points):
                continue
            home, away = int(g.home_id), int(g.away_id)
            h_p, a_p = prior_vector(home), prior_vector(away)
            h_c = model._latest_snapshot(scores, weeks, home, week)
            a_c = model._latest_snapshot(scores, weeks, away, week)
            hist_h, hist_a = histories_home[home], histories_away[away]
            venue = ((np.mean(hist_h) * len(hist_h)/(len(hist_h)+3) if hist_h else 0)
                     - (np.mean(hist_a) * len(hist_a)/(len(hist_a)+3) if hist_a else 0)) / 14.0
            if bool(g.neutral_site):
                venue = 0
            items.append({
                "season": year, "week": week, "game_id": str(int(g.game_id)),
                "home": str(g.home_team), "away": str(g.away_team),
                "home_points": float(g.home_points), "away_points": float(g.away_points),
                "home_win": int(g.home_points > g.away_points),
                "off_prior": h_p[0]-a_p[0], "off_current": h_c[0]-a_c[0],
                "def_prior": h_p[1]-a_p[1], "def_current": h_c[1]-a_c[1],
                "sos_prior": h_p[2]-a_p[2], "sos_current": h_c[2]-a_c[2],
                "venue": venue, "conference": model.conference_log_odds(g),
                "current_weight": model.current_season_weight(week)
            })
    return pd.DataFrame(items)


def predict(frame, w, season_adjust=0):
    cur = np.clip(frame.current_weight.to_numpy() + season_adjust, 0.10, 0.95)
    prior = 1 - cur
    offense = prior*frame.off_prior.to_numpy()+cur*frame.off_current.to_numpy()
    defense = prior*frame.def_prior.to_numpy()+cur*frame.def_current.to_numpy()
    sos = prior*frame.sos_prior.to_numpy()+cur*frame.sos_current.to_numpy()
    v = frame.venue.to_numpy()
    s = w[0]*offense + w[1]*defense + w[2]*v + w[3]*sos
    return expit(ALPHA*s + frame.conference.to_numpy())


def metrics(df, p):
    y = df.home_win.to_numpy().astype(int)
    if len(y) == 0:
        return None
    pred = p >= .5
    confidence = np.where(pred, p, 1-p)
    winner_correct = pred == y
    hi = confidence >= .8
    p = np.clip(p, 1e-12, 1-1e-12)
    return {
        "games": len(y), "wins": int(np.sum(winner_correct)),
        "accuracy": round(float(np.mean(winner_correct)), 6),
        "brier": round(float(np.mean((p-y)**2)), 7),
        "log_loss": round(float(np.mean(-y*np.log(p)-(1-y)*np.log1p(-p))), 7),
        "mean_confidence": round(float(np.mean(confidence)), 6),
        "high_confidence_games": int(np.sum(hi)),
        "high_confidence_wins": int(np.sum(winner_correct & hi)),
        "high_confidence_accuracy": round(float(np.mean(winner_correct[hi])), 6) if any(hi) else None,
    }


def evaluate(frame, w, season_adjust=0):
    p = predict(frame, w, season_adjust)
    result = {"all": metrics(frame,p)}
    for label, mask in [
        ("weeks_1_2", frame.week.le(2)),
        ("weeks_3_plus", frame.week.ge(3)),
        ("weeks_5_plus", frame.week.ge(5)),
        ("week_5", frame.week.eq(5)),
        ("week_6", frame.week.eq(6)),
        ("weeks_3_to_6", frame.week.between(3,6)),
        ("p4_g6_cross", frame.conference.abs().gt(0.01)),
        ("same_group_or_unknown", frame.conference.abs().lt(0.01)),
    ]:
        result[label] = metrics(frame[mask],p[mask.to_numpy()])
    return result


def compare_winners(frame, baseline_prob, candidate_prob, top_n=12):
    y = frame.home_win.to_numpy().astype(int)
    base = baseline_prob >= .5
    new = candidate_prob >= .5
    better = np.flatnonzero((new==y) & (base!=y))
    worse = np.flatnonzero((new!=y) & (base==y))
    def ex(indices):
        return [{"week": int(frame.iloc[i].week), "game": str(frame.iloc[i].away)+" at "+str(frame.iloc[i].home),
                 "actual_winner": str(frame.iloc[i].home if y[i] else frame.iloc[i].away),
                 "baseline": str(frame.iloc[i].home if base[i] else frame.iloc[i].away),
                 "candidate": str(frame.iloc[i].home if new[i] else frame.iloc[i].away),
                 "baseline_home_p": round(float(baseline_prob[i]),3),
                 "candidate_home_p": round(float(candidate_prob[i]),3)}
                for i in indices[:top_n]]
    return {"improved_count": len(better), "regressed_count": len(worse),
            "flipped_from_wrong_to_correct": ex(better),
            "flipped_from_correct_to_wrong": ex(worse)}


def main():
    all_seasons = {year: assemble_features(year) for year in (2024,2025,2026)}
    full = pd.concat(all_seasons.values(), ignore_index=True)
    base_predictions = {y: predict(f, WEIGHTS["baseline"]) for y,f in all_seasons.items()}
    # Check the exact production method for the same games rather than assuming parity.
    checks = {}
    for year in (2024,2025,2026):
        frame = all_seasons[year]
        # Compare V1.5 to feature-engine reconstruction on three representative weeks.
        sample_weeks = [w for w in (2,5,6) if w in set(frame.week)]
        current, prior = read_summary(None, year), read_summary(None, year-1)
        original = games_for(year)
        for week in sample_weeks:
            x = model.predict_week(current, prior, original, week, include_completed=True)
            x = x.set_index(x["Game ID"].astype(int))
            sample = frame[frame.week.eq(week)]
            assert all(gid in x.index for gid in sample.game_id.astype(int))
            from_production = x.loc[sample.game_id.astype(int), "Home Win %"].to_numpy()
            from_features = base_predictions[year][frame.week.eq(week).to_numpy()]
            diff = float(np.max(np.abs(from_production-from_features)))
            if diff > 1e-10:
                raise AssertionError(f"{year} week {week} mismatch {diff}")
            checks[f"{year}_week{week}"] = {"games":len(sample), "max_probability_difference":diff}

    variants = dict(WEIGHTS)
    variants.update({
        "current_season_plus_10pp": WEIGHTS["baseline"],
        "current_season_minus_10pp": WEIGHTS["baseline"],
    })
    results = []
    for name, w in variants.items():
        shift = .1 if name == "current_season_plus_10pp" else -.1 if name == "current_season_minus_10pp" else 0
        scores = {str(year): evaluate(frame, w, shift) for year,frame in all_seasons.items()}
        row = {"name":name, "weights":dict(zip(("offense","defense","venue","sos"), w)),
               "current_season_shift":shift, "scores":scores}
        b2024 = scores["2024"]["all"]
        baseline_2024 = next((e for e in results if e["name"]=="baseline"), None)
        if baseline_2024:
            base = baseline_2024["scores"]["2024"]["all"]
            row["improves_2024_brier"] = b2024["brier"] < base["brier"]
            row["improves_2024_accuracy"] = b2024["accuracy"] > base["accuracy"]
        results.append(row)
    baseline = results[0]
    # Select by Brier in 2024 among scenarios with accuracy no more than
    # 1 point worse. Tests on 2025 and 2026 are descriptive validation only.
    accepted = [x for x in results[1:] if
                x["scores"]["2024"]["all"]["brier"] < baseline["scores"]["2024"]["all"]["brier"]
                and x["scores"]["2024"]["all"]["accuracy"] >= baseline["scores"]["2024"]["all"]["accuracy"] - .01]
    selected = min(accepted, key=lambda x:x["scores"]["2024"]["all"]["brier"]) if accepted else None
    if selected:
        selected["flips_vs_baseline"] = {
            str(year): compare_winners(frame, base_predictions[year],
                                       predict(frame, tuple(selected["weights"].values()), selected["current_season_shift"]))
            for year, frame in all_seasons.items()
        }
    result = {
        "method":"Research-only exact production-feature reconstruction; 2024 candidate selection, report 2025/2026 as diagnostic validation.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_version":model.MODEL_VERSION,
        "feature_parity_checks":checks,
        "baseline":baseline,
        "selected_by_2024":selected,
        "all_variants_ranked_by_2024_brier":sorted(results,key=lambda x:x["scores"]["2024"]["all"]["brier"]),
        "limitations":[
            "Retrospective source data may be revised; 2025 was previously inspected and is not a clean holdout.",
            "The 2026 cohort includes completed games only, through Week 6. Future games are excluded.",
            "Multiple tried configurations create selection bias; modest historical gains must be verified prospectively.",
            "Conference calibration, within-unit offensive/defensive stat mixtures, prior Elo mixture, and sigmoid slope are held fixed.",
            "Week 6 market-odds comparison is separate; these tests measure straight-up accuracy and probability quality, not ATS or bet ROI.",
            "No production weights are changed."
        ],
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps({
        "feature_parity_checks":checks,
        "baseline":baseline["scores"],
        "selected_by_2024":None if not selected else {k:selected[k] for k in ("name","weights","current_season_shift","scores","flips_vs_baseline")},
        "top_variants":[{"name":x["name"],"scores":{year:x["scores"][year]["all"] for year in ("2024","2025","2026")}}
                        for x in result["all_variants_ranked_by_2024_brier"][:10]]
    },indent=2))


if __name__=="__main__":
    main()
