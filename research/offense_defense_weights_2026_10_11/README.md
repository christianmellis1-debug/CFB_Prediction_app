# Offense and defense internal weight sensitivity

**Status:** research only, October 11, 2026. The live Saturday Forecast V1.5 equation, Streamlit UI, and five official Value Shortlist tiers are unchanged.

## What was tested

39 **predefined** setups, each modifying only the internal weights for normalized adjusted EPA/play, success rate, explosive plays, and red-zone success. Separately tested offense, defense, and several joint weightings. Held main weights fixed at offense 35%, defense 35%, venue 20%, strength of schedule 10%. Kept the conference adjustment, season-blending schedule, prior-year 25% efficiency / 75% Elo, and probability calibration fixed.

The baseline is an exact numerical reconstruction of production V1.5. The component-level offensive and defensive current ratings, and previous-year efficiency component ratings, are verified against the production calculation. Weekly snapshots from the selected game's week are never used: only earlier-week snapshots qualify.

Seasons: 2024 = 752 games; 2025 = 762; 2026 = 329 completed games through Week 6. 2024 is used for exploratory candidate selection; 2025 and 2026 have been seen in earlier work and are **not pristine untouched test sets**. Retrospective source feeds may revise earlier values.

## Win accuracy

| Internal weights changed | 2024 | 2025 | 2026 through W6 | 2026 W6 record |
|---|---:|---:|---:|---:|
| Baseline: both 40/30/15/15 | 537/752 (71.4%) | 546/762 (71.7%) | 241/329 (73.3%) | 37/58 |
| Offense EPA 60%, success 20%, explosive 10%, red zone 10% | 537/752 (71.4%) | 544/762 (71.4%) | 242/329 (73.6%) | 37/58 |
| Defense EPA 30%, success 25%, explosive 15%, red zone 30% | 542/752 (72.1%) | 554/762 (72.7%) | 240/329 (73.0%) | 38/58 |
| Defense all four 25% | 538/752 (71.5%) | 550/762 (72.2%) | 240/329 (72.9%) | 37/58 |
| Both red zone 25% | 537/752 (71.4%) | 550/762 (72.2%) | 243/329 (73.9%) | 37/58 |
| Both explosive 30% | 531/752 (70.6%) | 535/762 (70.2%) | 244/329 (74.2%) | 38/58 |
| Offense explosive 30% | 532/752 (70.7%) | 542/762 (71.1%) | 245/329 (74.5%) | 40/58 |

## Probability quality (Brier score; lower is better)

| Internal weights changed | 2024 | 2025 | 2026 |
|---|---:|---:|---:|
| Baseline | .187816 | .182967 | .170812 |
| Offense EPA 60% | .187414 | .182799 | .169789 |
| Defense red zone 30% | .187369 | .185149 | .171395 |
| Defense all four 25% | .186930 | .184545 | .171959 |
| Both red zone 25% | .187606 | .184130 | .172383 |
| Both explosive 30% | .189214 | .184254 | .171547 |

2024's lowest Brier candidate satisfying the 1-percentage-point winner-accuracy tolerance was equal-weight defense. It worsened Brier in both later seasons, so it does **not** justify replacing the production configuration.

Offense EPA 60% improved Brier slightly in each season, but did not improve winner accuracy reliably and the absolute Brier differences are small. This is a reasonable prospectively monitored challenger, not a proven winner.

The Week 6 retrospective cohort is 58 games. The distinct pregame-frozen V1.5 forward test used 56 games; do not conflate the two cohorts. A short-span 40/58 success for more offensive explosive emphasis fails to establish a lasting advantage because earlier complete-season results regressed.

## Decision

Retain production V1.5 unchanged. Prospectively compare a small fixed set of challengers (offensive EPA 60%, defensive red-zone 30%, and defensive equal-weight), against the baseline on the same upcoming archived matchups. Track straight-up winner accuracy, Brier, high-confidence accuracy and calibration; monitor the model's disagreement with betting markets, but do not equate straight-up accuracy with ATS/ML ROI.

Full scenario, year, week, and subgroup data live in results.json. The full experiment is run.py, executed on the separate research branch by the GitHub Actions workflow.
