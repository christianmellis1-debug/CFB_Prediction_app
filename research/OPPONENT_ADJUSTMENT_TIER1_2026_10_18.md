# Opponent-adjusted Tier 1 value: historical investigation (2026-10-18)

## Status and conclusion
**Research only. No production changes.** Opponent-adjusted scoring residuals did not show a sufficiently stable improvement in Tier 1 ATS performance to warrant deployment. The 2026 full-game projected-margin MAE improved by 0.172 points against Elo-only and only 0.008 points against raw scoring, while 2025 error was slightly higher than Elo-only. Archived spread-based filters were inconsistent across years.

## Method
- Years: 2024 used for training; 2025 held out. Retrain on 2024–25, hold out 2026.
- FBS regular season, same P4/P4 or G6/G6, non-neutral matches with 2+ earlier same-season FBS games for both teams. No same-week or future games are used.
- Three ridge-regression projected-margin specifications with fixed regularization: Elo-only, Elo plus raw historical home/away normalized scoring residuals, Elo plus prior-opponent-adjusted scoring residuals.
- Opponent adjustment uses opponents' **pregame Elo at the time each prior game was played**, so high scoring against strong opponents is credited more and scores conceded to them are penalized less.
- Fixed constants: FBS scoring baseline 28 points, historical Elo 0.035 margin points/rating, venue 3 points, history shrink n/(n+3), ridge penalty 10. Constants and candidate edge thresholds (0,2,3,5 points) are research specification, not optimized on held-out ATS selections.
- Rebuilt the live Tier 1 five-statistical-advantages plus home field rule for each past week; archived market home-team spreads were used for reconstructed historical results. No bookmaker odds prices were used to infer ROI.
- October 17 2026 is reported separately using 10 immutable archived Tier 1 picks and their original lines. Earlier years and other 2026 weeks remain retrospective reconstructions.

## Holdout projected-margin error
| Holdout | Games | Elo-only MAE | Raw scoring MAE | Opponent-adjusted MAE | Elo RMSE | Raw RMSE | Opponent RMSE |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2025 (2024 trained) | 557 | **12.360** | 12.426 | 12.368 | 15.579 | 15.595 | 15.580 |
| 2026 (2024+25 trained) | 218 | 12.542 | 12.378 | **12.370** | 15.789 | 15.599 | **15.536** |

## Tier 1 ATS - 6/6 home selections
The below candidates require at least two earlier verified FBS games from both teams. This covers 75/78 six-of-six games in 2025 and 30/33 in 2026. Results are retrospective, except locked 2026 Week 7.

| Group | 6/6 baseline | Opponent edge >0 | Opponent edge >2 | Opponent edge >3 | Opponent edge >5 |
|---|---|---|---|---|---|
| 2025 reconstructed, eligible | 42–33 (56.0%) | **11–14 (44.0%)** | 7–10 (41.2%) | 6–5 (54.5%) | 4–3 (57.1%) |
| 2026 reconstructed, eligible | 16–14 (53.3%) | 10–6 (62.5%) | 9–5 (64.3%) | 7–5 (58.3%) | 4–4 (50.0%) |
| 2026 Week 7 locked | 3–7 (30.0%) | 2–2 (50.0%) | 2–2 (50.0%) | **0–2 (0.0%)** | 0–1 (0.0%) |

'Edge >3' is a genuinely strict greater-than threshold, no rounding before qualification. Selection rate falls sharply; no evidence of repeatable return. 2026 16–14 reconstructed covers a different set of picks to the prospective-archive-plus-Week6-and-earlier retrospective 17–14 previously discussed.

## Locked Week 7 opponent-adjusted projected value and outcomes
| Home selection | Spread | Opponent-adjusted edge (points) | Result |
|---|---:|---:|---|
| Bowling Green | -6.5 | +3.8 | Loss |
| LSU | -16.5 | -4.7 | Win |
| Maryland | -5.5 | -4.4 | Loss |
| Duke | -3.0 | +6.2 | Loss |
| Georgia | -19.5 | -0.3 | Loss |
| Oregon State | -18.5 | -2.9 | Loss |
| South Florida | -20.5 | +2.4 | Win |
| Miami | -20.5 | -1.8 | Loss |
| North Dakota State | -14.5 | -4.7 | Loss |
| UCLA | -2.5 | +2.8 | Win |

## Interpretation
Opponent adjustment did not eliminate outright losses on Duke or Bowling Green, and its >3-point screen kept both while omitting the actual South Florida and UCLA covers. **Recommendation: do not deploy opponent adjustment alone as Tier 1 gate.** Research alternative independently-calibrated spread-cover probability / distributional margin model or interaction with pregame matchup differential. Benchmark against simply fading/selecting the other side and the sportsbook implied 50/50 ATS baseline, with several untouched future weeks.

## Audit and limitations
- Live production unchanged. This script exists on a non-merged research branch.
- Selection metric conditions are historical reconstructions except for the frozen October 17 card; revised underlying source feeds and historically archived market spreads may differ from actual pregame lines.
- Main GitHub Actions test suite also reports 4 unrelated stale UI/copy assertions, while the standalone opponent adjustment audit test itself passed.
- Test log: https://github.com/christianmellis1-debug/CFB_Prediction_app/actions/runs/39136814749
