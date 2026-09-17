# Power Four versus Group of Five calibration audit

Research date: September 17, 2026. Production model remains V1.4.

## Scope and data

Completed 2024 and 2025 regular-season FBS games, using conference membership
recorded for each season. Power Four: ACC, Big Ten, Big 12, SEC. Group of Five:
American Athletic, Conference USA, Mid-American, Mountain West, Sun Belt.
Independents and the two-member Pac-12 are excluded from this comparison.
This historical cohort is not identical to the realigned 2026 Group of Six.
FCS games are excluded. Bowl/playoff games are excluded from model fitting.

Schedules: https://github.com/sportsdataverse/cfbfastR-data/tree/main/schedules/csv

Weekly summaries: https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/cfb_team_summaries_weekly

## Findings

| Season | P4 wins | Games | Actual win rate | Model mean P4 probability |
|---|---:|---:|---:|---:|
| 2024 | 78 | 86 | 90.7% | 72.3% |
| 2025 | 77 | 89 | 86.5% | 70.3% |
| Combined | 155 | 175 | 88.6% | — |

At home, P4 teams won 131 of 141 games (92.9%). Away, they won 22 of 31
(71.0%). The remaining three games were neutral-site (two P4 wins). Venue and
the teams selected for each type of matchup matter; these are not causal estimates.
Postseason cross-group records were 3/8 in 2024 and 7/10 in 2025, illustrating
why the regular-season base rate should not be assigned to every matchup.

## Candidate experiment

Fit one additive P4-versus-G5 log-odds offset on 2024 by minimizing log loss.
The fitted offset is 1.5560572697633837. Apply it unchanged to 2025; other
matchups receive no adjustment. This is a holdout for this new parameter,
not a claim that the existing model was never developed using 2025 information.

2025 cross-group results (89 games):

| Metric | Existing model | Candidate |
|---|---:|---:|
| Brier score (lower is better) | 0.10909 | 0.08981 |
| Log loss (lower is better) | 0.36393 | 0.28590 |
| Correct winner picks | 80/89 | 77/89 |

The candidate improves probability scoring, but loses three correct picks.
Across all 762 regular-season FBS games, Brier improves 0.18432 to 0.18207,
while winner accuracy declines 73.10% to 72.70%. No profitability claim is made;
this experiment does not test available betting odds or achievable returns.

## Texas–UTSA diagnostic

The September 17 feed reproduces Texas at 61.4849% for 2026 Week 3. The
experimental offset would produce 88.3273%; this is not deployed or independently
validated for this game. Texas's through-week-2 snapshot has adjusted EPA, while
UTSA's snapshot has no adjusted EPA or opponent-strength values. The existing
model mixes Texas's adjusted defensive EPA (-0.07511) with UTSA's unadjusted
defensive EPA (-0.712156). Missing opponent-strength values contribute neutral
standardized scores. These differently adjusted inputs warrant further testing.

## Decision

Do not deploy a blanket conference boost yet. Results justify investigating a
conference-aware calibration layer and consistent opponent-adjusted inputs.
Validate on additional seasons and account for 2026 realignment before changing
production. Historical feed snapshots may have been revised; reconstructed
pregame-week predictions are not archived predictions made before kickoff.

## Reproduction

Run `python backtests/conference_audit.py` from the repo root with pandas, numpy,
and scipy installed. Place `schedule2024.csv` and `schedule2025.csv` from the
schedule source above at the root. Download the 2023, 2024 and 2025 weekly
summary release CSVs as `summary2023.csv`, `summary2024.csv`, `summary2025.csv`.
Use model.py blob `f595d73c624a6f0bdfa3bc7df8da226f98dc2702` and the current
app.py `augment_missing_summaries` function. Only snapshots before each target
week enter current-season features. The script produces per-game CSVs and
`backtests/conference_results.json`.
