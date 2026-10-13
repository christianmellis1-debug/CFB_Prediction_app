# Saturday Forecast — Test B: Venue adjustment validation

**Date:** 2026-10-13. **Status:** research-only; do not deploy the selected candidate.

## Scope and controls

Compared the current V1.5 raw venue adjustment to 56 combinations (8 signal definitions × 7 weight choices). Venue weight is a coefficient on the historical home-margin/road-margin signal, not a literal statement that home field explains 20% of variance.

- Same underlying pregame predictions for each matchup: reconstructed V1.5 from available historical summaries in 2024–2025; immutable V1.5 pregame snapshots for 2026 Week 5–6.
- Use **only** completed earlier-week regular-season FBS games as historical venue inputs; exclude prior neutral-site games from venue margins and assign zero venue impact to target neutral-site matchups.
- Current model signal: `(mean home margin × n/(n+3) − mean away margin × n/(n+3)) / 14`.
- Challengers: change the current venue weight to 0, 0.05, 0.10, 0.15, 0.20, 0.30 or 0.40; increase shrinkage denominator from 3 to 5; replace historical margins with **opponent-adjusted residual margins** based on each prior game's pregame Elo (25 Elo points per scoreboard point) and a 2.5-point generic home allowance; restore 0, 2.5 or 4 points of generic home advantage in the new residual signal; 50/50 mix of raw/residual signals; flat home advantage of 2.5 or 4 points.
- Candidates are applied on the **log-odds scale**, replacing the original 0.20 raw-venue contribution while leaving offense, defense, SOS, conference calibration and the baseline probability otherwise unchanged.
- Select by lowest **2024 Brier score**. Evaluate the single selected setting unchanged in 2025 and 2026; do not retune to either.

## 2024-selected challenger

**Elo-residual home/road margins +4-point baseline; coefficient 0.20.** The initial residual removes 2.5 points as part of calculating expected prior-game margin, then the candidate adds 4 points to the matchup venue signal. These fixed point conversions are exploratory heuristics, not independently fitted point spreads.

| Year / same games | Current V1.5 | Challenger | Current Brier | Challenger Brier |
|---|---:|---:|---:|---:|
| 2024, 752 | 536–216 (71.28%) | 544–208 (72.34%) | 0.187913 | 0.187159 |
| 2025, 762 | 546–216 (71.65%) | 544–218 (71.39%) | 0.183029 | 0.184659 |
| 2026 Weeks 5–6, 112 | 77–35 (68.75%) | 79–33 (70.54%) | 0.208983 | 0.207090 |

**Critical failure:** Accuracy, Brier score and log loss all worsened in 2025. The 2026 aggregate lift came entirely from Week 5.

| 2026 week | Frozen baseline | Challenger | Changes |
|---|---:|---:|---|
| Week 5 | 42–14 | 45–11 | 3 previously wrong picks corrected |
| Week 6 | 35–21 | 34–22 | 1 previously right pick changed to wrong |

Detailed Week 5 corrected winners: Air Force over Navy, Kentucky over South Carolina, San Diego State over Texas State. Week 6 erroneous change: Temple over UConn.

## Weight-only stress test

Holding the existing raw venue signal fixed:

| Weight | 2024 correct / 752 | 2025 correct / 762 | 2026 correct / 112 |
|---|---:|---:|---:|
| 0.00, remove venue | 528 | 538 | 76 |
| 0.10 | 529 | 541 | 78 |
| **0.20, current** | **536** | 546 | 77 |
| 0.30 | 534 | **549** | 77 |
| 0.40 | 526 | 551 | 77 |

Lower weights generally worsened both historical seasons. Increasing to 0.30–0.40 helped 2025 but hurt 2024; in 2026 it didn't increase winner accuracy and worsened Brier calibration versus current. The current 0.20 weight therefore remains preferable as the unchanged production default.

Increasing the shrinkage denominator to 5 with coefficient 0.30 gave 536/752, 547/762, and 77/112, while Brier changes were very small in 2024–2025 and **worse** in 2026. This result was identified after seeing all three samples, so it is another exploratory candidate, not valid independent confirmation.

## Data/model caveats

- Historical V1.5 probabilities for 2024–2025 were reconstructed using presently published weekly summary data. They are **not** originally archived game-day predictions, and values can diverge from earlier backtest snapshots as data are revised. The selection is conditional on the current snapshot and is not an untouched model-wide holdout; 2025 outcomes were also used in earlier V1.5 development.
- The 2026 baseline *is* taken from the archived pregame snapshot; the challenger venue calculation is retrospective using updated schedule records, so it is not a prospective 2026 forecast.
- Historical Elo-based margin expectation uses a heuristic 25 Elo points per scoreboard point and a 2.5-point generic home allowance. The selected 4-point replacement prior is also exploratory. It does not adjust for injuries, roster changes, travel distance, game conditions or strength differences beyond Elo.
- No significance or profitability claim. Historical outcomes within weeks and conferences are correlated; scanning 56 configurations raises selection risk.

## Decision

**Do not replace the official venue calculation.** The 2024-optimal candidate does not generalize to 2025 and worsens the exact Week 6 we want to improve. Test A's opponent-adjusted recent offensive EPA remains separate and research-only; do not mix it with this venue adjustment without a new frozen A/B comparison.

Files: `research/test_b_venue.py` (reproducible backtest), `research/test_b_venue_results.json` (all 56 candidate metrics), `research/test_b_venue_games.csv` (1,626 game-level signal/prediction pairs), and `.github/workflows/research-test-b-venue.yml`. All are kept on `research/test-b-venue-calibration-2026-10-13`, not main.
