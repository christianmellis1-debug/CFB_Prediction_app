
import math
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy.special import expit, logit

MODEL_VERSION = "V1.5"

OFFENSE_WEIGHT = 0.35
DEFENSE_WEIGHT = 0.35
VENUE_WEIGHT = 0.20
SOS_WEIGHT = 0.10

PRIOR_EFF_WEIGHT = 0.25
PRIOR_ELO_WEIGHT = 0.75

CURRENT_SEASON_WEIGHTS = {
    1: 0.30, 2: 0.40, 3: 0.50, 4: 0.60, 5: 0.65,
    6: 0.70, 7: 0.75, 8: 0.80, 9: 0.85,
}
CURRENT_SEASON_WEIGHT_WEEK_10_PLUS = 0.90
CALIBRATION_SLOPE = 1.945

COMPONENT_SPEC = {
    "oe": ("adj_off_epa", 1, "EPAplay_off"),
    "os": ("success_off", 1, None),
    "ox": ("explosive_off", 1, None),
    "or": ("red_zone_success_off", 1, None),
    "de": ("adj_def_epa", -1, "EPAplay_def"),
    "ds": ("success_def", -1, None),
    "dx": ("explosive_def", -1, None),
    "dr": ("red_zone_success_def", -1, None),
    "so": ("off_strength_faced", 1, None),
    "sd": ("def_strength_faced", 1, None),
}


# Fitted on 2022–23 regular-season P5/G5 games; selected on 2024 and
# evaluated on 2025. See backtests/EXTENDED_CALIBRATION.md.
CONFERENCE_LOG_ODDS = 1.2610042485353463

def conference_log_odds(game):
    """Season-aware regular-season FBS correction; unknown classifications skip."""
    try:
        year = int(game.get("season"))
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if year < 2022 or str(game.get("season_type", "")).lower() != "regular":
        return 0.0
    if any(str(game.get(side + "_division", "")).lower() != "fbs" for side in ("home", "away")):
        return 0.0
    power = {"ACC", "Big Ten", "Big 12", "SEC"}
    group = {"American Athletic", "Conference USA", "Mid-American", "Mountain West", "Sun Belt"}
    if year <= 2023:
        power.add("Pac-12")
    elif year >= 2026:
        group.add("Pac-12")
    home = game.get("home_conference")
    away = game.get("away_conference")
    if home in power and away in group:
        return CONFERENCE_LOG_ODDS
    if away in power and home in group:
        return -CONFERENCE_LOG_ODDS
    return 0.0

def current_season_weight(week):
    week = int(week)
    if week >= 10:
        return CURRENT_SEASON_WEIGHT_WEEK_10_PLUS
    return CURRENT_SEASON_WEIGHTS[week]

def confidence_label(conf):
    if conf >= 0.90: return "Very High"
    if conf >= 0.80: return "High"
    if conf >= 0.70: return "Moderate"
    if conf >= 0.60: return "Lean"
    return "Toss-up"

def road_risk_label(predicted_side, confidence):
    if predicted_side != "Away":
        return "Normal"
    if confidence >= 0.80:
        return "Elevated"
    if confidence >= 0.60:
        return "Moderate"
    return "Normal"

def _zscore(v):
    sd = v.std(ddof=0)
    if not sd or np.isnan(sd):
        return pd.Series(np.zeros(len(v)), index=v.index)
    return ((v - v.mean()) / sd).fillna(0)

def build_weekly_scores(df):
    scores = {}
    weeks = defaultdict(list)
    for week, x in df.groupby("through_week"):
        z = {}
        for key, (col, sign, fallback) in COMPONENT_SPEC.items():
            if col not in x.columns:
                raise ValueError(f"Missing required column: {col}")
            v = pd.to_numeric(x[col], errors="coerce")
            if fallback and fallback in x.columns:
                v = v.where(v.notna(), pd.to_numeric(x[fallback], errors="coerce"))
            z[key] = _zscore(v * sign)

        tmp = pd.DataFrame({"team_id": x["team_id"].astype(int)})
        tmp["off"] = 0.40*z["oe"] + 0.30*z["os"] + 0.15*z["ox"] + 0.15*z["or"]
        tmp["defn"] = 0.40*z["de"] + 0.30*z["ds"] + 0.15*z["dx"] + 0.15*z["dr"]
        tmp["sos"] = 0.50*z["so"] + 0.50*z["sd"]

        for _, r in tmp.iterrows():
            tid = int(r["team_id"])
            w = int(week)
            scores[(tid, w)] = (float(r["off"]), float(r["defn"]), float(r["sos"]))
            weeks[tid].append(w)

    for tid in weeks:
        weeks[tid] = sorted(set(weeks[tid]))
    return scores, weeks

def build_prior_profiles(prior_summary, schedule):
    # A 2026 FBS entrant must not inherit an FCS efficiency/Elo prior.
    entrants = set()
    years = pd.to_numeric(schedule.get('season', pd.Series(dtype=float)), errors='coerce')
    if years.eq(2026).any():
        for side in ('home', 'away'):
            names = schedule[side + '_team'].astype(str).str.casefold()
            entrants.update(pd.to_numeric(schedule.loc[names.isin(['sacramento state', 'sac state', 'sacramento state hornets']), side + '_id'], errors='coerce').dropna().astype(int))
    prior_summary = prior_summary[~pd.to_numeric(prior_summary.team_id, errors='coerce').isin(entrants)].copy()
    p_scores, p_weeks = build_weekly_scores(prior_summary)
    prior_eff = {tid: p_scores[(tid, max(ws))] for tid, ws in p_weeks.items()}

    rows = []
    for _, g in schedule.iterrows():
        if pd.notna(g.get("home_pregame_elo")):
            rows.append((int(g["home_id"]), g["home_team"], g["home_pregame_elo"]))
        if pd.notna(g.get("away_pregame_elo")):
            rows.append((int(g["away_id"]), g["away_team"], g["away_pregame_elo"]))

    elo = pd.DataFrame(rows, columns=["team_id","team","elo"]).dropna()
    if elo.empty:
        raise ValueError("No usable preseason Elo values were found in the schedule.")
    elo = elo.groupby(["team_id","team"], as_index=False).first()
    elo["elo_z"] = _zscore(pd.to_numeric(elo["elo"], errors="coerce"))
    prior_elo = dict(zip(elo["team_id"].astype(int), elo["elo_z"]))

    def prior_vector(tid):
        if tid in entrants:
            return (0.0, 0.0, 0.0)
        eff = prior_eff.get(tid, (0.0,0.0,0.0))
        ez = prior_elo.get(tid, 0.0)
        return (
            PRIOR_EFF_WEIGHT*eff[0] + PRIOR_ELO_WEIGHT*ez,
            PRIOR_EFF_WEIGHT*eff[1] + PRIOR_ELO_WEIGHT*ez,
            eff[2]
        )
    return prior_vector

def _latest_snapshot(scores, weeks, tid, game_week):
    eligible = [w for w in weeks.get(tid, []) if w < game_week]
    return scores[(tid, max(eligible))] if eligible else (0.0,0.0,0.0)

def _completed_history(schedule, target_week):
    hist = schedule.copy()
    if "completed" in hist.columns:
        completed = hist["completed"].astype(str).str.lower().isin(["true","t","1","yes","y"])
        hist = hist[completed]
    hist = hist[pd.to_numeric(hist["week"], errors="coerce") < target_week]
    hist = hist[pd.notna(hist["home_points"]) & pd.notna(hist["away_points"])]

    home_hist = defaultdict(list)
    road_hist = defaultdict(list)

    sort_cols = ["week"] + (["start_date"] if "start_date" in hist.columns else [])
    for _, g in hist.sort_values(sort_cols).iterrows():
        if bool(g.get("neutral_site", False)):
            continue
        h = int(g["home_id"]); a = int(g["away_id"])
        diff = float(g["home_points"] - g["away_points"])
        home_hist[h].append(diff)
        road_hist[a].append(-diff)
    return home_hist, road_hist


def pick_narrative(winner, opponent, confidence, contributions):
    """Describe signed model contributions, not causal or matchup-specific claims."""
    labels = {
        "offense": "an edge on offense",
        "defense": "an edge on defense",
        "schedule": "the difficulty of each team's schedule",
        "venue": "past results at home and on the road",
        "conference": "how teams from these conferences have performed historically",
    }
    support = sorted(((k, v) for k, v in contributions.items() if v > 1e-8),
                     key=lambda item: item[1], reverse=True)
    against = sorted(((k, v) for k, v in contributions.items() if v < -1e-8),
                     key=lambda item: item[1])
    if support:
        reasons = " and ".join(labels[k] for k, _ in support[:2])
        text = f"{winner} gets the nod mainly from {reasons}."
    else:
        text = f"The model has no meaningful separation between {winner} and {opponent}; this is effectively a coin flip."
    if against:
        text += f" The biggest factor working against this pick is {labels[against[0][0]]}, which favors {opponent}."
    if confidence < 0.60 and support:
        text += " The overall edge is small, so this remains a toss-up."
    text += f" The model estimates {winner} has a {confidence:.0%} chance to win."
    return text

def predict_week(current_summary, prior_summary, schedule, target_week, include_completed=False):
    from matchup_advantages import normalize_fbs_schedule
    schedule = normalize_fbs_schedule(schedule)
    target_week = int(target_week)
    scores, weeks = build_weekly_scores(current_summary)
    prior_vector = build_prior_profiles(prior_summary, schedule)
    home_hist, road_hist = _completed_history(schedule, target_week)

    week_games = schedule[pd.to_numeric(schedule["week"], errors="coerce") == target_week].copy()
    if "completed" in week_games.columns and not include_completed:
        completed = week_games["completed"].astype(str).str.lower().isin(["true","t","1","yes","y"])
        if (~completed).any():
            week_games = week_games[~completed]

    cur = current_season_weight(target_week)
    prv = 1-cur
    rows = []

    for _, g in week_games.iterrows():
        h = int(g["home_id"]); a = int(g["away_id"])
        hs = _latest_snapshot(scores, weeks, h, target_week)
        aws = _latest_snapshot(scores, weeks, a, target_week)
        hp = prior_vector(h); ap = prior_vector(a)

        hoff = prv*hp[0] + cur*hs[0]
        hdef = prv*hp[1] + cur*hs[1]
        hsos = prv*hp[2] + cur*hs[2]
        aoff = prv*ap[0] + cur*aws[0]
        adef = prv*ap[1] + cur*aws[1]
        asos = prv*ap[2] + cur*aws[2]

        hm = np.mean(home_hist[h]) if home_hist[h] else 0.0
        am = np.mean(road_hist[a]) if road_hist[a] else 0.0
        venue_signal = (
            hm*len(home_hist[h])/(len(home_hist[h])+3)
            - am*len(road_hist[a])/(len(road_hist[a])+3)
        ) / 14.0

        neutral = bool(g.get("neutral_site", False))
        venue_component = 0.0 if neutral else VENUE_WEIGHT*venue_signal

        score_diff = (
            OFFENSE_WEIGHT*(hoff-aoff)
            + DEFENSE_WEIGHT*(hdef-adef)
            + venue_component
            + SOS_WEIGHT*(hsos-asos)
        )

        raw_home_prob = 1/(1+math.exp(-1.10*score_diff))
        home_prob = float(expit(CALIBRATION_SLOPE * logit(np.clip(raw_home_prob, 1e-6, 1-1e-6)) + conference_log_odds(g)))
        away_prob = 1-home_prob

        if home_prob >= .5:
            winner = g["home_team"]; side = "Home"; conf = home_prob
        else:
            winner = g["away_team"]; side = "Away"; conf = away_prob

        direction = 1 if side == "Home" else -1
        contributions = {
            "offense": direction * CALIBRATION_SLOPE * 1.10 * OFFENSE_WEIGHT * (hoff-aoff),
            "defense": direction * CALIBRATION_SLOPE * 1.10 * DEFENSE_WEIGHT * (hdef-adef),
            "schedule": direction * CALIBRATION_SLOPE * 1.10 * SOS_WEIGHT * (hsos-asos),
            "venue": direction * CALIBRATION_SLOPE * 1.10 * venue_component,
            "conference": direction * conference_log_odds(g),
        }
        opponent = g["away_team"] if side == "Home" else g["home_team"]
        explanation = pick_narrative(winner, opponent, conf, contributions)
        rows.append({
            "Game ID": g.get("game_id"),
            "Week": target_week,
            "Away Team": g["away_team"],
            "Home Team": g["home_team"],
            "Away Win %": away_prob,
            "Home Win %": home_prob,
            "Predicted Winner": winner,
            "Confidence": conf,
            "Confidence Label": confidence_label(conf),
            "Venue Risk": road_risk_label(side, conf),
            "Predicted Side": side,
            "Neutral Site": neutral,
            "Model Version": MODEL_VERSION,
            "Pick Explanation": explanation,
        })

    return pd.DataFrame(rows).sort_values("Confidence", ascending=False).reset_index(drop=True) if rows else pd.DataFrame()



def add_waterfall_value(predictions, schedule, boxes, week, weather_checks=None, published_summary=None):
    """Annotate predictions with the waterfall without replacing the core model winner."""
    from matchup_advantages import (build_advantages, build_waterfall_profiles,
                                    build_tier5_four_factor, select_waterfall, cross_tier_matches)

    result = predictions.copy()
    profiles = build_waterfall_profiles(schedule, boxes, week)
    advantage_checks = build_advantages(schedule, boxes, week)
    tier5_checks = build_tier5_four_factor(schedule, published_summary, week) if published_summary is not None else {}
    card = select_waterfall(result, schedule, profiles, advantage_checks=advantage_checks,
                            weather_checks=weather_checks, tier5_checks=tier5_checks)
    cross_tiers = cross_tier_matches(
        result, schedule, profiles, advantage_checks=advantage_checks,
        weather_checks=weather_checks, tier5_checks=tier5_checks,
    )
    defaults = {
        'Game of Week': False, 'Game of Week Team': '', 'Game of Week Tier Count': 0,
        'Game of Week Tiers': '',
        'Value Selected': False, 'Value Tier': '', 'Value Stage': 0,
        'Value Pick': '', 'Value Side': '', 'Value Line': 'Unavailable',
        'Value Price': 'Unavailable', 'Value Market': '', 'Value Source': '',
        'Value Band': '', 'Value Reason': '', 'Value Rank': 0,
        'Value Result': 'Pending', 'Bet Signal': 'Pass',
    }
    for key, default in defaults.items():
        result[key] = default

    ids = pd.to_numeric(result.get('Game ID', pd.Series(index=result.index, dtype=float)), errors='coerce')
    for gid, overlap in cross_tiers.items():
        if not overlap.get('qualifies'):
            continue
        try:
            game_id = int(gid)
        except (TypeError, ValueError):
            continue
        mask = ids.eq(game_id)
        result.loc[mask, 'Game of Week'] = True
        result.loc[mask, 'Game of Week Team'] = overlap.get('team', '')
        result.loc[mask, 'Game of Week Tier Count'] = int(overlap.get('count', 0))
        result.loc[mask, 'Game of Week Tiers'] = ', '.join(
            f"Tier {stage}" for stage in overlap.get('stages', [])
        )

    for pick in card:
        mask = ids.eq(pick['Game ID'])
        for key, value in pick.items():
            if key != 'Game ID':
                result.loc[mask, key] = value
        result.loc[mask, 'Value Selected'] = True
        result.loc[mask, 'Bet Signal'] = pick['Value Tier']

    if 'Status' in result:
        final = result['Value Selected'] & result.Status.eq('Final')

        # Moneyline tiers continue to grade the selected straight-up winner.
        ml = final & result['Value Market'].eq('Moneyline')
        decisive = ml & result.get('Actual Winner', pd.Series('—', index=result.index)).notna()
        decisive &= ~result.get('Actual Winner', pd.Series('—', index=result.index)).isin(['Tie', '—', ''])
        result.loc[decisive, 'Value Result'] = np.where(
            result.loc[decisive, 'Value Pick'].eq(result.loc[decisive, 'Actual Winner']),
            'Correct', 'Incorrect')
        if 'Actual Winner' in result:
            result.loc[ml & result['Actual Winner'].eq('Tie'), 'Value Result'] = 'Not graded'

        # Stage 1 grades against the stored spread, including pushes.
        if 'game_id' in schedule:
            game_ids = pd.to_numeric(schedule['game_id'], errors='coerce')
            for idx in result.index[final & result['Value Market'].eq('Spread')]:
                try:
                    gid = int(ids.loc[idx])
                    spread = float(str(result.loc[idx, 'Value Line']).replace('+', '').replace('−', '-'))
                except (TypeError, ValueError, OverflowError):
                    result.loc[idx, 'Value Result'] = 'Not graded'
                    continue
                match = schedule.loc[game_ids.eq(gid)]
                if len(match) != 1:
                    result.loc[idx, 'Value Result'] = 'Not graded'
                    continue
                game = match.iloc[0]
                try:
                    home_points = float(game['home_points'])
                    away_points = float(game['away_points'])
                except (KeyError, TypeError, ValueError):
                    result.loc[idx, 'Value Result'] = 'Not graded'
                    continue
                if not np.isfinite(home_points) or not np.isfinite(away_points):
                    result.loc[idx, 'Value Result'] = 'Not graded'
                    continue
                margin = home_points - away_points if result.loc[idx, 'Value Side'] == 'Home' else away_points - home_points
                ats = margin + spread
                result.loc[idx, 'Value Result'] = 'Correct' if ats > 1e-10 else 'Incorrect' if ats < -1e-10 else 'Push'

    result.attrs['waterfall'] = {
        'count': len(card), 'minimum': 12, 'maximum': 18,
        'shortfall': max(0, 12-len(card)),
        'method': 'waterfall-v5-official-tier4-heavy-favorite-su-tier5-four-factor-su', 'retrospective': True,
    }
    return result


def waterfall_scenario_rows(predictions):
    """Adapt selected sides/prices for the existing simulation, on a copy only."""
    result = predictions[predictions['Value Selected']].copy()
    result['Predicted Winner'] = result['Value Pick']
    result['Predicted Side'] = result['Value Side']
    result['Pick Result'] = result['Value Result']
    result['Bet Market'] = result['Value Market']
    result['Bet Display'] = result['Value Pick'].astype(str) + ' ' + result['Value Line'].astype(str)
    result['Bet Line'] = result['Value Price']
    result['ML Source'] = result['Value Source']
    result['Confidence'] = np.where(result['Value Side'].eq('Home'), result['Home Win %'], result['Away Win %'])
    return result
