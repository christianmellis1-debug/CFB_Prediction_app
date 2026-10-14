# Saturday Forecast — Small weight adjustment experiment (2026 Weeks 3–6)

**Research-only backtest. No production V1.5, Test C blend, winner selection, or six betting tiers changed.**

## Research question and data

Can changing one or two percentage points in the current Saturday Forecast weights improve correct straight-up winners on **2026 Weeks 3–6**?

The current engine consists of:
- Base V1.5: **35% offense + 35% defense + 20% venue + 10% SOS**. These four weights sum to 100%.
- Market blend: **16.927926947215113% V1.5 + 83.072073052784887% same-book no-vig moneyline**.

**Two independent levers were tested:**

1. **Blend sensitivity:** shift ±0.5 to ±5 percentage points between V1.5 and the market while retaining the same two game probabilities, same 221 quoted matchups, and the same final outcomes.
2. **V1.5 component sensitivity:** shift **±1 or ±2 percentage points** between every pair of offense/defense/venue/SOS, maintaining the total at exactly 100%. **24** alternatives plus current baseline, and pass each through the **unchanged 16.93%/83.07% blend**.

**Cohort and provenance:** Exactly 221 same-game records, 53 games Week 3, 56 games each Weeks 4, 5, 6, matched to publicly archived DraftKings opening moneylines. Weeks 3–4 used retrospective V1.5 reconstruction; Weeks 5–6 used **112 immutable pre-kickoff V1.5 predictions** from the frozen snapshot archive and incremental candidate log-odds effects reconstructed separately. This procedure is a retrospective weight sensitivity, not a genuine prospective candidate test; source sportsbook open-line timestamp is not independently verified.

Original V1.5 **158–63**; official Test C **169–52 (76.47%)**, Brier **0.1701468**, log loss **0.5078483**.

## Experiment A: shift the V1.5/market blend by a few percentage points

| V1.5 share | Market share | W–L | Brier | Change in winners |
|---:|---:|---:|---:|---:|
| 14.93% | 85.07% | 169–52 | 0.1700623 | 0 |
| 15.93% | 84.07% | 169–52 | 0.1701026 | 0 |
| **16.93%** | **83.07%** | **169–52** | **0.1701468** | **Baseline** |
| 17.93% | 82.07% | 169–52 | 0.1701951 | 0 |
| 18.93% | 81.07% | 169–52 | 0.1702473 | 0 |

Across **±5 percentage points**, no setting improves upon 169 correct games; at certain extremes, one previously correct winner flips into a loss. The modest Brier gain from slightly more market weight (−2 points to V1.5) is just **0.0000845**, unlikely to justify changing the coefficients on a resolved season.

## Experiment B: small transfers among internal V1.5 components

All configurations total 100%. Winners below are the **final Test C picks** after the fixed 16.93/83.07 blend.

| V1.5 offense | Defense | Venue | SOS | Test C W–L | Test C Brier |
|---:|---:|---:|---:|---:|---:|
| **35%** | **35%** | **20%** | **10%** | **169–52** | 0.1701468 |
| 36% | 34% | 20% | 10% | 169–52 | 0.1700746 |
| **37%** | **33%** | 20% | 10% | **169–52** | **0.1700030** |
| 35% | 33% | 22% | 10% | 169–52 | 0.1700689 |
| 35% | 33% | 20% | 12% | 169–52 | 0.1700427 |
| 33% | 37% | 20% | 10% | **167–54** | 0.1702934 |

**Of 25 configurations:** 19 finish **169–52**, five finish **168–53**, one finishes **167–54**. **No tested variation fixes a Test C losing selection.** Some more-defense variants flip two previously correct Week 5 picks into losses: Navy at Air Force and Old Dominion at Georgia State.

The **37/33 offense–defense candidate** has the lowest pooled Brier (0.1700030 vs 0.1701468, a difference of **0.0001438** or about **0.085%** relative improvement). It also slightly improves Test C Brier in each of Weeks 3–6:

| Week | Test C baseline record | 37/33 record | Baseline Brier | 37/33 Brier |
|---|---:|---:|---:|---:|
| 3 (retrospective) | 45–8 | 45–8 | 0.1208681 | 0.1207187 |
| 4 (retrospective) | 46–10 | 46–10 | 0.1613343 | 0.1611874 |
| 5 (frozen base) | 41–15 | 41–15 | 0.1837256 | 0.1836399 |
| 6 (frozen base) | 37–19 | 37–19 | 0.2120193 | 0.2118258 |

**Independent V1.5 consideration:** increasing offense to 37% and decreasing defense to 33% improves *V1.5's* Brier from roughly **0.187794 to 0.186681**, but its own correctly predicted winners decline **158→157** on the same cohort. That loss is masked by the market-dominated Test C forecast (unchanged winner picks). This is another reason not to equate a tiny lower Brier on retrospectively selected weights with a reliable future improvement.

## Decision

**Leave both weight sets unchanged in production.** The precise user-requested ±1–2 point variations did **not improve outright winner accuracy** on any of the 221 games. The current 16.93/83.07 final blend is stable within this small neighborhood.

The 37% offense/33% defense candidate is a reasonable **shadow-only calibration experiment**, but its tiny post-hoc Brier gain and worse independent V1.5 accuracy do not justify immediately replacing the official 35/35/20/10 baseline. A true forward test is needed before adjustment, especially since 2024/25 and most 2026 records have already informed model development.

These results do not support changing or retraining the six independent betting tiers.

## Reproducible research

- `research/weight_micro_w3w6.py`: source V1.5 baseline and 24 alternative predictions reconstructed week-by-week against pinned public schedule and cumulative summaries; after Week 4 re-anchor estimated candidate differences to the originally frozen V1.5 pregame predictions.
- `research/weight_micro_w3w6_results.json`: all variant weights, all four week records, Brier, log loss, winner flips, fixes/breaks.
- `research/weight_micro_w3w6_games.csv`: every matched game and predicted win probability under every candidate.
- `research/test_micro_v15_component_weights.py`: independent direct component contribution and log-odds grid replay, cross-checking exact baseline parity with V1.5.
- `.github/workflows/research-weight-micro-w3w6.yml` and `.github/workflows/research-micro-v15-weights.yml`: reproducible research checks on this branch only.

Source [original matched 2026 W3–6 research](https://github.com/christianmellis1-debug/CFB_Prediction_app/blob/research/test-c-head-to-head-weeks3-6-2026-10-13/research/test_c_head_to_head_weeks3_6_games.csv).

**No production or tier changes were made.**
