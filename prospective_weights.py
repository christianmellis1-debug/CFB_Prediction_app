"""Frozen, research-only V1.5 offense/defense internal-weight challengers.

Reuses the production model's home-win probability and changes ONLY the four
within-unit feature coefficients. Baseline and three challenger versions are
computed from the same earlier-week standardized inputs. Not a production
model replacement or an official Value Shortlist selection.
"""
import math
from collections import defaultdict
import numpy as np
import pandas as pd
from scipy.special import expit, logit
import model_v1_5 as model

BASE = (0.40, 0.30, 0.15, 0.15)
FIELDS = ("epa", "success", "explosive", "red_zone")
CHALLENGERS = {
    "V1.5 current": (BASE, BASE),
    "Offensive EPA 60%": ((0.60, 0.20, 0.10, 0.10), BASE),
    "Defensive red zone 30%": (BASE, (0.30, 0.25, 0.15, 0.30)),
    "Balanced defense 25%": (BASE, (0.25, 0.25, 0.25, 0.25)),
}
EXPERIMENT = "cfb-internal-weights-v1-2026-10-12"
ALPHA = model.CALIBRATION_SLOPE * 1.10

assert all(all(abs(sum(w)-1) < 1e-10 and min(w) >= 0 for w in pair)
           for pair in CHALLENGERS.values())


def component_vectors(summary):
    """Same per-week z scoring and EPA fallback as production model V1.5."""
    scores, weeks = {}, defaultdict(list)
    for through_week, frame in summary.groupby("through_week"):
        z = {}
        for key in ("oe", "os", "ox", "or", "de", "ds", "dx", "dr"):
            col, sign, fallback = model.COMPONENT_SPEC[key]
            values = pd.to_numeric(frame[col], errors="coerce")
            if fallback and fallback in frame:
                values = values.where(values.notna(),
                                      pd.to_numeric(frame[fallback], errors="coerce"))
            z[key] = model._zscore(values * sign)
        for idx, tid in frame["team_id"].items():
            tid = int(tid)
            week = int(through_week)
            o = np.array([z[k].loc[idx] for k in ("oe", "os", "ox", "or")], dtype=float)
            d = np.array([z[k].loc[idx] for k in ("de", "ds", "dx", "dr")], dtype=float)
            scores[(tid, week)] = (o, d)
            weeks[tid].append(week)
    return scores, {tid: sorted(set(items)) for tid, items in weeks.items()}


def latest(scores, weeks, tid, cutoff=None):
    eligible = [w for w in weeks.get(int(tid), ()) if cutoff is None or w < int(cutoff)]
    if not eligible:
        return np.zeros(4), np.zeros(4)
    return scores[(int(tid), max(eligible))]


def prior_excluded_ids(schedule):
    """Match 2026 entrant filtering in model.build_prior_profiles."""
    years = pd.to_numeric(schedule.get("season", pd.Series(dtype=float)), errors="coerce")
    if not years.eq(2026).any():
        return set()
    excluded = set()
    for side in ("home", "away"):
        names = schedule[side + "_team"].astype(str).str.strip().str.casefold()
        matches = names.isin(("sacramento state", "sac state", "sacramento state hornets"))
        excluded.update(pd.to_numeric(
            schedule.loc[matches, side + "_id"], errors="coerce"
        ).dropna().astype(int))
    return excluded


def validate_component_parity(summary, vectors, weeks, label):
    """Fail rather than archive subtly different features from production."""
    original, original_weeks = model.build_weekly_scores(summary)
    for tid in weeks:
        for week in weeks[tid]:
            own = vectors[tid, week]
            true = original[tid, week]
            for position in (0, 1):
                if not math.isclose(float(np.asarray(BASE) @ own[position]),
                                    float(true[position]), rel_tol=0, abs_tol=1e-10):
                    raise ValueError(f"{label} feature parity failure for team {tid} week {week}")


def pregame_predictions(current, prior, schedule, target_week, baseline_frame=None):
    """Return every available game's four probabilities, preserving production V1.5."""
    from matchup_advantages import normalize_fbs_schedule
    schedule = normalize_fbs_schedule(schedule)
    week = int(target_week)
    if baseline_frame is None:
        baseline_frame = model.predict_week(current, prior, schedule, week, include_completed=True)
    if baseline_frame.empty:
        return {}

    cur_scores, cur_weeks = component_vectors(current)
    excluded = prior_excluded_ids(schedule)
    adjusted_prior = prior.loc[
        ~pd.to_numeric(prior["team_id"], errors="coerce").isin(excluded)
    ].copy()
    prior_scores, prior_weeks = component_vectors(adjusted_prior)
    validate_component_parity(current, cur_scores, cur_weeks, "current")
    validate_component_parity(adjusted_prior, prior_scores, prior_weeks, "prior")

    cur_weight = model.current_season_weight(week)
    previous_weight = 1 - cur_weight
    base_by_id = {}
    for _, row in baseline_frame.iterrows():
        try:
            gid = str(int(row["Game ID"]))
            prob = float(row["Home Win %"])
            if not (0 < prob < 1 and math.isfinite(prob)) or gid in base_by_id:
                raise ValueError("Invalid or duplicate baseline prediction")
            base_by_id[gid] = prob
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            raise ValueError("Baseline predictions cannot be verified") from exc

    target = schedule[pd.to_numeric(schedule["week"], errors="coerce").eq(week)]
    predictions = {}
    for _, g in target.iterrows():
        gid = str(int(g["game_id"]))
        if gid not in base_by_id:
            continue
        hid, aid = int(g["home_id"]), int(g["away_id"])
        hcur = latest(cur_scores, cur_weeks, hid, week)
        acur = latest(cur_scores, cur_weeks, aid, week)
        hprior = latest(prior_scores, prior_weeks, hid) if hid not in excluded else (np.zeros(4), np.zeros(4))
        aprior = latest(prior_scores, prior_weeks, aid) if aid not in excluded else (np.zeros(4), np.zeros(4))
        delta_cur = (hcur[0] - acur[0], hcur[1] - acur[1])
        delta_prior = (hprior[0] - aprior[0], hprior[1] - aprior[1])

        baseline_prob = base_by_id[gid]
        scores = {}
        for name, (off, defense) in CHALLENGERS.items():
            do = np.asarray(off) - np.asarray(BASE)
            dd = np.asarray(defense) - np.asarray(BASE)
            movement = cur_weight * (
                model.OFFENSE_WEIGHT * (do @ delta_cur[0]) +
                model.DEFENSE_WEIGHT * (dd @ delta_cur[1])
            ) + previous_weight * model.PRIOR_EFF_WEIGHT * (
                model.OFFENSE_WEIGHT * (do @ delta_prior[0]) +
                model.DEFENSE_WEIGHT * (dd @ delta_prior[1])
            )
            prob = float(expit(logit(baseline_prob) + ALPHA * movement))
            if not math.isfinite(prob):
                raise ValueError("Nonfinite challenger probability")
            scores[name] = prob
        if abs(scores["V1.5 current"] - baseline_prob) > 1e-12:
            raise AssertionError("Production baseline changed in challenger evaluation")
        predictions[gid] = scores
    return predictions


def configuration():
    return {
        name: {"offense": dict(zip(FIELDS, off)),
               "defense": dict(zip(FIELDS, defense))}
        for name, (off, defense) in CHALLENGERS.items()
    }
