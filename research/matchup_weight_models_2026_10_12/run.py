"""Research-only matchup-weighted CFB predictions and fixed hybrid tests.

Strict pregame inputs: matchup_advantages.build_advantages reads FBS games from
earlier weeks ONLY; latest summaries are likewise strictly earlier-week.
Train only 2022-2023, select on 2024, describe 2025 and 2026 diagnostics.
Production predictions, waterfall tiers, and app.py are never changed.
"""
import json
import math
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit, logit

import model_v1_5 as model
from matchup_advantages import (build_advantages, normalize_fbs_schedule,
                                conference_group)
from shadow_inputs import download_schedule, read_summary
from capture_value import boxes

OUT = Path("research/matchup_weight_models_2026_10_12/results.json")
FEATURES = ("rushing", "passing", "explosive", "red_zone", "turnover")
WEIGHTS = {
    "balanced": (.20, .20, .20, .20, .20),
    "run_first": (.40, .20, .15, .15, .10),
    "pass_first": (.20, .40, .15, .15, .10),
    "explosive_first": (.20, .20, .40, .10, .10),
    "redzone_first": (.20, .20, .15, .35, .10),
    "turnover_first": (.20, .20, .15, .10, .35),
    "football_30_25_20_15_10": (.30, .25, .20, .15, .10),
}
BLENDS = (0.20, 0.40, 0.60)
assert all(np.isclose(sum(w), 1.0) and min(w) >= 0 for w in WEIGHTS.values())


def schedule_for(year):
    s = download_schedule(year)
    s = s[s.season_type.astype(str).str.lower().eq("regular")].copy()
    s = normalize_fbs_schedule(s)
    for c in ("season", "week", "game_id", "home_id", "away_id", "home_points", "away_points"):
        s[c] = pd.to_numeric(s[c], errors="coerce")
    s = s.dropna(subset=["game_id", "week", "home_id", "away_id"])
    return s.sort_values("start_date", kind="stable")


def known_group(g, year):
    """Only same-group research; exclude era-ambiguous Pac-12 classification."""
    if year < 2026 and (g.home_conference == "Pac-12" or g.away_conference == "Pac-12"):
        return False
    home = conference_group(g.home_conference, g.home_team)
    away = conference_group(g.away_conference, g.away_team)
    return home is not None and home == away


def latest_raw(summary, week):
    """Latest strictly earlier-week published advanced stats, keyed by team."""
    before = summary[
        pd.to_numeric(summary["through_week"], errors="coerce").lt(int(week))
    ].copy()
    if before.empty:
        return {}
    before = before.sort_values("through_week", kind="stable")
    return {
        int(x.team_id): x for _, x in
        before.drop_duplicates("team_id", keep="last").iterrows()
    }


def difference(home, away, ho, ao, hd, ad):
    """Offense-vs-opponent-defense contrast, with lower defense allowed better.

    Opponent defensive explosive/red-zone inputs are success rates *allowed*.
    The relative matchup contrast is:
      (home offensive rate - away defensive allowed rate)
        - (away offensive rate - home defensive allowed rate).
    """
    values = (float(home[ho]), float(away[ao]),
              float(home[hd]), float(away[ad]))
    if not all(math.isfinite(v) for v in values):
        return None
    return (values[0] - values[3]) - (values[1] - values[2])


def extra_features(raw, home_id, away_id):
    h, a = raw.get(int(home_id)), raw.get(int(away_id))
    if h is None or a is None:
        return None
    result = []
    for off, defense in (("explosive_off", "explosive_def"),
                         ("red_zone_success_off", "red_zone_success_def")):
        needed = [h[off], a[off], h[defense], a[defense]]
        if not all(pd.notna(v) and math.isfinite(float(v)) for v in needed):
            return None
        # Offense minus opposing defense allowed, then opposite direction.
        result.append((float(h[off])-float(a[defense]))
                      -(float(a[off])-float(h[defense])))
    return result


def build_year(year):
    schedule = schedule_for(year)
    current = read_summary(None, year)
    previous = read_summary(None, year-1)
    box = boxes(year)
    out, coverage = [], {}
    for week in sorted(schedule.week.dropna().astype(int).unique()):
        if year == 2026 and week > 6:
            break
        if week < 2:
            continue  # No current-season, prior-game matchup history yet
        week_games = schedule[schedule.week.eq(week)]
        week_games = week_games[
            week_games.home_points.notna() & week_games.away_points.notna()
        ]
        week_games = week_games[
            week_games.completed.astype(str).str.lower().isin(
                ("true", "t", "1", "1.0", "yes", "y")
            )
        ]
        if week_games.empty:
            continue
        predictions = model.predict_week(
            current, previous, schedule, week, include_completed=True
        )
        base = {str(int(x["Game ID"])): float(x["Home Win %"])
                for _, x in predictions.iterrows()}
        # Existing app production function: validates full prior FBS history,
        # rushing and completion rates, both-side turnovers and exact team IDs.
        prior_stats = build_advantages(schedule, box, week)
        advanced = latest_raw(current, week)
        counts = {"completed":0, "eligible_same_group":0,
                  "five_metric_available":0, "advanced_available":0,
                  "both_available":0}
        for _, g in week_games.iterrows():
            counts["completed"] += 1
            if float(g.home_points)==float(g.away_points):
                continue
            if not known_group(g,year):
                continue
            counts["eligible_same_group"] += 1
            gid=str(int(g.game_id))
            record=prior_stats.get(gid,{})
            if record.get("status")!="ok":
                continue
            counts["five_metric_available"] += 1
            extra=extra_features(advanced,g.home_id,g.away_id)
            if extra is None:
                continue
            counts["advanced_available"] += 1
            if gid not in base:
                continue
            home,away=record["home"],record["away"]
            # Source identities per original matchups:
            # 0 rushing matchup estimates, 1 passing completion matchup,
            # 4 turnover margin per prior FBS game.
            x=[
                float(home[0]-away[0]),
                float(home[1]-away[1]),
                float(extra[0]),
                float(extra[1]),
                float(home[4]-away[4]),
            ]
            if not all(math.isfinite(z) for z in x):
                continue
            counts["both_available"] += 1
            out.append({
                "year":year,"week":week,"game_id":gid,
                "home":str(g.home_team),"away":str(g.away_team),
                "home_win":int(float(g.home_points)>float(g.away_points)),
                "base_home_probability":base[gid],
                **dict(zip(FEATURES,x))
            })
        coverage[str(week)] = counts
    if not out:
        raise ValueError(f"No eligible complete matchup feature games in {year}")
    return pd.DataFrame(out),coverage


def fit_normalization(train):
    x=train[list(FEATURES)].to_numpy(dtype=float)
    center=np.mean(x,axis=0)
    scale=np.std(x,axis=0)
    if np.any(scale <= 1e-10):
        raise ValueError("Invalid train-set feature dispersion")
    return center,scale


def standardized(frame,mean,sd):
    return (frame[list(FEATURES)].to_numpy(dtype=float)-mean)/sd


def fit_logistic(x, y):
    """Fit one intercept and one nonnegative slope on 2022-23 only."""
    def objective(params):
        log_odds=params[0]+params[1]*x
        return float(np.mean(np.logaddexp(0,log_odds)-y*log_odds)
                     +0.0005*params[1]**2)
    result=minimize(
        objective, x0=np.asarray([0.,0.7]), method="L-BFGS-B",
        bounds=[(-3,3),(0,6)],
    )
    if not result.success or not np.all(np.isfinite(result.x)):
        raise RuntimeError("Matchup probability training failed")
    return [float(x) for x in result.x]


def measures(frame,p):
    y=frame.home_win.to_numpy(dtype=int)
    p=np.clip(p,1e-8,1-1e-8)
    success=np.where(p>=.5,1,0)==y
    hi=np.maximum(p,1-p)>=.80
    return {
        "games":int(len(y)), "wins":int(success.sum()),
        "accuracy":round(float(success.mean()),6),
        "brier":round(float(np.mean((p-y)**2)),7),
        "log_loss":round(float(np.mean(-(y*np.log(p)+(1-y)*np.log1p(-p)))),7),
        "high_confidence_games":int(hi.sum()),
        "high_confidence_wins":int(np.sum(success & hi)),
    }


def summarize(frame,p):
    result={"all":measures(frame,p)}
    for name,mask in (
        ("weeks_3_plus",frame.week.ge(3)),
        ("weeks_5_plus",frame.week.ge(5)),
        ("week_5",frame.week.eq(5)),
        ("week_6",frame.week.eq(6)),
    ):
        if mask.any():
            result[name]=measures(frame[mask],p[mask.to_numpy()])
        else:
            result[name]=None
    return result


def compare_years(years,cfg,weights,mean,sd):
    records={}
    for year,frame in years.items():
        x=standardized(frame,mean,sd) @ np.asarray(weights)
        params=cfg
        matchup=expit(params[0]+params[1]*x)
        baseline=frame.base_home_probability.to_numpy(dtype=float)
        source={"baseline":baseline,"matchup":matchup}
        for blend in BLENDS:
            source[f"hybrid_{int(blend*100)}"]=expit(
                (1-blend)*logit(np.clip(baseline,1e-8,1-1e-8))
                +blend*logit(np.clip(matchup,1e-8,1-1e-8)))
        records[str(year)] = {name:summarize(frame,p) for name,p in source.items()}
    return records


def main():
    data,coverage={},{}
    for year in (2022,2023,2024,2025,2026):
        data[year],coverage[str(year)]=build_year(year)
    train=pd.concat([data[2022],data[2023]],ignore_index=True)
    mean,sd=fit_normalization(train)
    x_train=standardized(train,mean,sd)
    y_train=train.home_win.to_numpy(dtype=int)
    all_tests=[]
    for name,weights in WEIGHTS.items():
        coefs=fit_logistic(x_train @ np.asarray(weights),y_train)
        scores=compare_years(data,coefs,weights,mean,sd)
        for pred in ("matchup","hybrid_20","hybrid_40","hybrid_60"):
            all_tests.append({
                "id":f"{name}_{pred}", "features":dict(zip(FEATURES,weights)),
                "trained_logit":dict(zip(("intercept","slope"),coefs)),
                "method":pred, "scores":{year:value[pred] for year,value in scores.items()}
            })
    baseline={str(year):summarize(frame,frame.base_home_probability.to_numpy(dtype=float))
              for year,frame in data.items()}
    base24=baseline["2024"]["all"]
    candidates=[t for t in all_tests if
                t["scores"]["2024"]["all"]["brier"] < base24["brier"] and
                t["scores"]["2024"]["all"]["accuracy"] >= base24["accuracy"]-.01]
    chosen=min(candidates,key=lambda t:t["scores"]["2024"]["all"]["brier"]) if candidates else None
    output={
        "design":"Research only: matchups same-group P4/P4 or G6/G6, data strictly earlier-week, parameters fitted 2022-2023, candidate selected 2024, 2025 and 2026 diagnostics.",
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "normalization":{"source":"2022-2023 training cohort only","means":dict(zip(FEATURES,mean.tolist())),
                         "stds":dict(zip(FEATURES,sd.tolist()))},
        "year_coverage":coverage,
        "graded_games":{str(y):len(data[y]) for y in data},
        "baseline":baseline,
        "candidates":all_tests,
        "selected_2024":chosen,
        "limitations":[
            "Retrospective public statistics can be revised and differ from original pregame feeds.",
            "Same-group matchups only; Notre Dame is P4 for this research, Pac-12 in 2022-25 excluded due to historical conference mapping.",
            "We use prior-week FBS box-score games and advanced summaries; missing history is an exclusion, not a losing pick.",
            "No bet lines, ATS results, or hypothetical betting ROI evaluated.",
            "2025/2026 have been analyzed before and are not pristine blind holdouts.",
            "Matchup score is a research probability independently calibrated on 2022-2023; hybrid blends are log-odds weighted, not direct probability arithmetic.",
            "A single selected winner among many candidates is likely optimistic; prospective lock-before-kickoff validation is required.",
            "No changes to live V1.5, waterfall Value Shortlist, or Streamlit."
        ],
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(output,indent=2,allow_nan=False)+"\n")
    print(json.dumps({
        "coverage":output["graded_games"],
        "baseline":{k:v["all"] for k,v in baseline.items()},
        "selected":None if chosen is None else {
            "id":chosen["id"],
            "features":chosen["features"],
            "trained_logit":chosen["trained_logit"],
            "scores":{k:v["all"] for k,v in chosen["scores"].items()},
        },
        "top_2024":[{"id":x["id"],"metrics":{yr:sc["all"] for yr,sc in x["scores"].items()}}
                    for x in sorted(all_tests,key=lambda x:x["scores"]["2024"]["all"]["brier"])[:8]],
    },indent=2))


if __name__=="__main__":
    main()
