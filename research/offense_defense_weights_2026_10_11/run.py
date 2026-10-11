"""Research-only sensitivity of the FOUR component weights inside V1.5 offense/defense.

Uses production V1.5 as an exact baseline; mathematically adjusts its log-odds
for changes to standardized individual component weights. All source snapshots
are strictly prior-week; prior-year team ratings change by 25% of their
efficiency movement, preserving unchanged 75% Elo and missing-team logic.
No production files or official picks are modified.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit, logit

from shadow_inputs import read_summary
import model_v1_5 as model
from research.weight_sensitivity_2026_10_11.run import (
    assemble_features, games_for, predict as baseline_predict, metrics,
    compare_winners, WEIGHTS, ALPHA,
)

OUTPUT = Path("research/offense_defense_weights_2026_10_11/results.json")
BASE = (0.40, 0.30, 0.15, 0.15)
MAINS = WEIGHTS["baseline"]

# Predeclare modest/large departures, alongside mechanisms to test.
VARIANTS = {
    "baseline": BASE,
    "epa_50": (.50, .25, .15, .10),
    "epa_60": (.60, .20, .10, .10),
    "success_45": (.30, .45, .15, .10),
    "success_50": (.25, .50, .15, .10),
    "explosive_30": (.35, .25, .30, .10),
    "explosive_35": (.30, .25, .35, .10),
    "redzone_25": (.35, .25, .15, .25),
    "redzone_30": (.30, .25, .15, .30),
    "equal_four": (.25, .25, .25, .25),
    "epa_success_85": (.45, .40, .10, .05),
}
assert all(all(v >= 0 for v in w) and abs(sum(w) - 1) < 1e-9
           for w in VARIANTS.values())

# Fixed non-optimized candidates: offense-only, defense-only, and a small
# predefined set of two-sided combinations; all evaluated before selection.
PLANS = [("baseline", "baseline", "baseline", "baseline")]
for key in list(VARIANTS)[1:]:
    PLANS.append(("offense_" + key, key, "baseline", "offense-only"))
    PLANS.append(("defense_" + key, "baseline", key, "defense-only"))
for key in ("epa_50", "epa_60", "success_45", "success_50",
            "explosive_30", "explosive_35", "redzone_25", "redzone_30",
            "equal_four", "epa_success_85"):
    PLANS.append(("both_" + key, key, key, "both"))
for offense, defense in [
    ("epa_50", "success_45"),
    ("success_45", "epa_50"),
    ("epa_50", "explosive_30"),
    ("explosive_30", "epa_50"),
    ("epa_success_85", "explosive_30"),
    ("success_45", "redzone_25"),
    ("redzone_25", "success_45"),
    ("explosive_30", "redzone_25"),
]:
    PLANS.append((f"off_{offense}_def_{defense}", offense, defense, "mixed"))
assert len(PLANS) == len(set(p[0] for p in PLANS))


def standardize_components(summary):
    """Replicate model._zscore and fallback semantics, week by week."""
    scores = {}
    weeks = {}
    keys = ("oe", "os", "ox", "or", "de", "ds", "dx", "dr")
    for through_week, portion in summary.groupby("through_week"):
        z = {}
        for key in keys:
            col, direction, fallback = model.COMPONENT_SPEC[key]
            values = pd.to_numeric(portion[col], errors="coerce")
            if fallback and fallback in portion:
                values = values.where(values.notna(), pd.to_numeric(portion[fallback], errors="coerce"))
            z[key] = model._zscore(values * direction)
        for ix, tid in zip(portion.index, portion.team_id):
            team_id, week = int(tid), int(through_week)
            off = np.asarray([z[k].loc[ix] for k in keys[:4]], dtype=float)
            defense = np.asarray([z[k].loc[ix] for k in keys[4:]], dtype=float)
            scores[team_id, week] = (off, defense)
            weeks.setdefault(team_id, []).append(week)
    for team in weeks:
        weeks[team] = sorted(set(weeks[team]))
    return scores, weeks


def get_z_snapshot(scores, weeks, tid, cutoff=None):
    available = weeks.get(tid, [])
    if cutoff is not None:
        available = [wk for wk in available if wk < cutoff]
    if not available:
        return np.zeros(4, dtype=float), np.zeros(4, dtype=float)
    return scores[(tid, max(available))]


def component_rows(year, frame):
    current, prior = read_summary(None, year), read_summary(None, year - 1)
    games = games_for(year)
    cur_scores, cur_weeks = standardize_components(current)
    prior_scores, prior_weeks = standardize_components(prior)
    games_by_id = {str(int(g.game_id)): g for _, g in games.iterrows()
                   if pd.notna(g.get("game_id"))}
    prior_blocked = set()
    if year == 2026:
        for _, g in games.iterrows():
            for side in ("home", "away"):
                if str(g[side+"_team"]).strip().casefold() in (
                        "sacramento state", "sac state", "sacramento state hornets"):
                    prior_blocked.add(int(g[side+"_id"]))

    fields = ("off_current", "def_current", "off_prior", "def_prior")
    out = {f: [] for f in fields}
    missing = 0
    for game_id, week in zip(frame.game_id, frame.week):
        g = games_by_id.get(str(game_id))
        if g is None:
            missing += 1
            raise RuntimeError(f"Unmatched game {game_id}")
        home, away = int(g.home_id), int(g.away_id)
        hc = get_z_snapshot(cur_scores, cur_weeks, home, int(week))
        ac = get_z_snapshot(cur_scores, cur_weeks, away, int(week))
        hp = (np.zeros(4), np.zeros(4)) if home in prior_blocked else get_z_snapshot(prior_scores, prior_weeks, home)
        ap = (np.zeros(4), np.zeros(4)) if away in prior_blocked else get_z_snapshot(prior_scores, prior_weeks, away)
        for i, part in enumerate(("off", "def")):
            out[part+"_current"].append(hc[i]-ac[i])
            out[part+"_prior"].append(hp[i]-ap[i])

    inputs = {f: np.vstack(values) for f, values in out.items()}
    # Strong independent parity check: the component-level reconstruction
    # must produce the same CURRENT-season strength as production V1.5.
    maxdiff = {}
    for label in ("off", "def"):
        b = np.asarray(BASE)
        recalculated = inputs[label+"_current"] @ b
        production = frame[label+"_current"].to_numpy()
        difference = float(np.max(np.abs(recalculated - production)))
        maxdiff[label+"_current"] = difference
        if difference > 1e-10:
            raise AssertionError(f"{year}: component parity mismatch {label}: {difference}")
    return inputs, maxdiff


def adjusted_probabilities(frame, inputs, baseline_probability, offense, defense):
    change_off = np.asarray(offense) - np.asarray(BASE)
    change_def = np.asarray(defense) - np.asarray(BASE)
    cur = frame.current_weight.to_numpy()
    prv = 1-cur
    # Prior efficiency is 25% and prior preseason Elo 75%; change only prior efficiency.
    delta_o = cur * (inputs["off_current"] @ change_off) + prv * 0.25 * (inputs["off_prior"] @ change_off)
    delta_d = cur * (inputs["def_current"] @ change_def) + prv * 0.25 * (inputs["def_prior"] @ change_def)
    changed_logit = logit(np.clip(baseline_probability, 1e-12, 1-1e-12)) + ALPHA * (
        MAINS[0] * delta_o + MAINS[1] * delta_d)
    return expit(changed_logit)


def breakdown(frame, p):
    parts = {"all": metrics(frame, p)}
    for name, mask in [
        ("weeks_3_plus", frame.week.ge(3)),
        ("week_5", frame.week.eq(5)),
        ("week_6", frame.week.eq(6)),
        ("weeks_5_plus", frame.week.ge(5)),
        ("cross_conference_group", frame.conference.abs().gt(0.01)),
        ("non_cross_group", frame.conference.abs().lt(0.01))
    ]:
        subset = frame[mask]
        parts[name] = metrics(subset, p[mask.to_numpy()])
    return parts


def main():
    years = (2024,2025,2026)
    frames = {yr: assemble_features(yr) for yr in years}
    inputs_and_parity = {yr: component_rows(yr, frames[yr]) for yr in years}
    base_prob = {yr: baseline_predict(frames[yr], MAINS) for yr in years}
    # Baseline prediction math must remain unchanged within floating precision.
    for yr in years:
        p = adjusted_probabilities(frames[yr], inputs_and_parity[yr][0],
                                    base_prob[yr], BASE, BASE)
        if float(np.max(np.abs(p-base_prob[yr]))) > 1e-10:
            raise AssertionError(f"Baseline mismatch in {yr}")
    results = []
    for name, ok, dk, group in PLANS:
        ow, dw = VARIANTS[ok], VARIANTS[dk]
        scores = {}
        predictions = {}
        for year in years:
            f = frames[year]
            predictions[year] = adjusted_probabilities(
                f, inputs_and_parity[year][0], base_prob[year], ow, dw)
            scores[str(year)] = breakdown(f, predictions[year])
        results.append({
            "name": name, "group":group,
            "offense": dict(zip(("epa","success","explosive","redzone"),ow)),
            "defense": dict(zip(("epa","success","explosive","redzone"),dw)),
            "scores": scores
        })
    baseline = results[0]
    base24=baseline["scores"]["2024"]["all"]
    eligible=[r for r in results[1:] if
              r["scores"]["2024"]["all"]["brier"] < base24["brier"] and
              r["scores"]["2024"]["all"]["accuracy"] >= base24["accuracy"]-.01]
    chosen = min(eligible,key=lambda r:r["scores"]["2024"]["all"]["brier"]) if eligible else None
    if chosen:
        chosen_plan=next(plan for plan in PLANS if plan[0] == chosen["name"])
        chosen["flips"]= {
            str(year):compare_winners(
                frames[year],base_prob[year],
                adjusted_probabilities(frames[year], inputs_and_parity[year][0],base_prob[year],
                                       VARIANTS[chosen_plan[1]],VARIANTS[chosen_plan[2]]),30)
            for year in years}
    result={
        "created_at":datetime.now(timezone.utc).isoformat(),
        "status":"RESEARCH ONLY - production model and value picks unchanged",
        "method":"Reconstruct exact V1.5 baseline; change only predeclared z-scored 4-factor mix in offense and defense; prior-season efficiency changed proportionally, pregame cutoff strictly earlier-week.",
        "games_by_season":{str(y):len(frames[y]) for y in years},
        "parity":{str(y):inputs_and_parity[y][1] for y in years},
        "tests":len(results),
        "selected_by_2024_brier_gate":chosen,
        "baseline":baseline,
        "all_results":results,
        "limitations":[
            "All historical seasons 2024-2026 have previously been examined in project research: neither 2025 nor 2026 is a pristine held-out season.",
            "2026 games only through completed Week 6. Retrospective source revisions can change forecasts.",
            "Multiple hypothesis testing can overfit the 2024 selection season; a good 2024 score is not proof of future improvement.",
            "Unchanged overall weights, conference term, calibration slope, current/prior season blend, SOS, venue, and preseason Elo.",
            "A straight-up win result is not ATS profitability; no betting return is claimed.",
            "Base rating features are standardized separately at each through-week, so raw rate scales are not directly comparable."
        ]
    }
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    def small(row):
        return {"name":row["name"],"group":row["group"],"offense":row["offense"],"defense":row["defense"],
                "metrics":{yr: {key:row["scores"][yr]["all"][key]
                                for key in ("games","wins","accuracy","brier","log_loss")}
                           for yr in ("2024","2025","2026")},
                "week6_2026":row["scores"]["2026"]["week_6"]}
    print(json.dumps({"parity":result["parity"], "tests":len(results),
          "baseline":small(baseline), "chosen":small(chosen) if chosen else None,
          "top_2024":list(map(small,sorted(results,key=lambda r:r["scores"]["2024"]["all"]["brier"])[:12])),
          "top_2025":list(map(small,sorted(results,key=lambda r:r["scores"]["2025"]["all"]["brier"])[:8])),
          "top_2026":list(map(small,sorted(results,key=lambda r:r["scores"]["2026"]["all"]["brier"])[:8]))},indent=2))


if __name__=="__main__":
    main()
