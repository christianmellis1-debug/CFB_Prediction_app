# Historical full-season decision: 16.93% V1.5 / 83.07% market blend

**Research completed October 13, 2026. Result: keep Test C as the leading shadow challenger; do NOT replace live V1.5 solely on these retrospective results.**

## Locked formulas and source data

Same-game no-vig sportsbook probability = implied home moneyline / (implied home + implied away).

`Test C P(home) = 0.16927926947215113 × P(V1.5 home) + 0.83072073052784887 × P(market home)`.

Pick winner using the blended home probability at 50%; evaluate Brier and log loss on the same home's final-result binary outcome. The coefficient was **frozen before this analysis** and is not reoptimized on these historical results. The market is **ESPN BET opening lines** (home and away from the same book), taken from archived ESPN game JSON. V1.5's 2024/2025 probabilities are retrospective reconstructed predictions using the currently published weekly historical statistical summaries, *not* original saved pre-kickoff model snapshots. Historical archive opening-odds timestamps could not be independently authenticated.

Matched **2024/2025 regular-season FBS games**, the same source pairs as the historical Test C warning replication. Exactly **1,437 of 1,514** reconstructed FBS matchups have valid archived primary provider two-sided opening odds: 717 in 2024, 720 in 2025. Evaluate **exactly the same matchups** for both models and each market-only comparator. Price omissions are not random; heavily favored games are often missing price pairs.

## Matched quoted games: final records

| Season | Games | V1.5 | Test C blend | Pure sportsbook | Additional correct winners |
|---|---:|---:|---:|---:|---:|
| 2024 | 717 | 506–211 (70.57%) | 509–208 (70.99%) | 510–207 (71.13%) | +3 |
| 2025 | 720 | 504–216 (70.00%) | 527–193 (73.19%) | 524–196 (72.78%) | +23 |
| **Combined** | **1,437** | **1,010–427 (70.29%)** | **1,036–401 (72.09%)** | **1,034–403 (71.96%)** | **+26** |

The blend switches **218** historical winners, correcting **122** original V1.5 mistakes while introducing **96** newly wrong selections. In 2024, **53 fixes / 50 breaks**, only **+3**. In 2025, **69 fixes / 46 breaks**, **+23**.

- Exact paired two-sided McNemar/binomial p ≈ **0.8439 in 2024**, **0.0398 in 2025**, **0.0902 combined**. The combined accuracy gain **is not conventionally statistically conclusive**, and previous model design may have used these historical years.
- Descriptive 5,000-repeat **season-stratified week-cluster bootstrap** for the overall accuracy improvement **+1.81 percentage points**: approximate 95% interval **−0.06 to +3.80 points**. This interval includes zero, and even grouping by week does not fully account for teams appearing in multiple weeks.
- This result cannot establish definitively greater future straight-up winner accuracy.

## Probability quality (Brier; lower is better)

| Season | V1.5 | Test C | Brier improvement |
|---|---:|---:|---:|
| 2024 | 0.192427 | **0.183489** | 0.008937 |
| 2025 | 0.193357 | **0.182276** | 0.011081 |
| Combined | 0.192893 | **0.182882** | **0.010011** |

Combined reduction in Brier of about **5.2%** relative to V1.5. Combined log loss **0.565607 V1.5 vs 0.541515 blend**. Descriptive season-stratified week-cluster 95% bootstrap interval for **Brier improvement**: approximately **0.00503 to 0.01516**. This is more consistent than the winner-accuracy gains. That finding is conditional on retrospective source provenance and available market odds; a market-dominated estimate's advantage over an independent team-statistics model is not surprising.

Market alone goes **1,034–403**, only two fewer correct winners than the blend, and Brier **0.183401**, very close to blend **0.182882**. There is no persuasive evidence on these games that the exact **16.93%** weight is itself an optimal universal coefficient rather than a near-market heuristic.

## How the result changes through the season

| Weeks | 2024 V1.5 → blend | Change | 2025 V1.5 → blend | Change |
|---|---:|---:|---:|---:|
| 1–4 | 115 → 117 / 162 | +2 | 114 → 121 / 170 | +7 |
| 5–8 | 144 → 149 / 212 | +5 | 144 → 159 / 211 | **+15** |
| 9 and later | 247 → 243 / 343 | **−4** | 246 → 247 / 339 | +1 |

Most gain is in Weeks 1–8: **+9** in 2024, **+22** in 2025, combined **+29**. Week 9 onward combined **−3**. This is a reason to *study* a conditional early-season model, **not** to retune its weights on the same datasets.

## Missing odds, end-to-end comparison, and robustness

Full reconstructed model cohorts: 752 in 2024 (536 correct) and 762 in 2025 (546 correct). Of the **77 unpriced games**, V1.5 got **72 correct** (30/35 in 2024, 42/42 in 2025), so omitting missing odds causes material selection bias. A realistic **fallback to unchanged V1.5 for unpriced games** gives:
- 2024: **539/752 (71.7%)** versus full V1.5 **536/752 (71.3%)**, +3.
- 2025: **569/762 (74.7%)** versus full V1.5 **546/762 (71.7%)**, +23.
- Combined: **1,108/1,514 (73.2%)** versus **1,082/1,514 (71.5%)**, +26.

Fallback does not independently validate effectiveness on priced games; it merely reports the operational coverage policy correctly.

Price timing and source matter:
- Primary ESPN BET **opening**: 1,437 games, Test C **+26 winners**, Brier gain **0.010011**, paired p≈0.090.
- Primary ESPN BET **closing**: 1,425 games, Test C **+20 winners**, Brier gain **0.009603**, paired p≈0.179.
- Alternate archived ESPN Bet - Live Odds **opening**: 1,465 games, Test C **+28 winners**, Brier gain **0.010489**, paired p≈0.067.

These comparisons have overlapping-but-different game cohorts and *are not independent replications*. Provider also differs from the mostly DraftKings 2026 frozen forward experiment.

## Decision: production release gate is not cleared

**Do not automatically replace the live V1.5 predictor today.** The specified condition — **definitively better winner selection** — is not met on the full 2024/2025 historical sample. Stronger historical probability calibration is promising, but the 2024 winner count barely changes and the combined 95% interval includes no improvement.

The running 2026 shadow archive is already tracking genuine pregame V1.5-vs-Test C choices. Evaluate at least **four newly observed slates** and **200 matched graded predictions** from the date the challenger was formally designated, with an equal quote-time policy, matched same-game win accuracy, paired tests, confidence-calibration/Brier, coverage and loss-breakdown checks. Keep the fixed 16.93%/83.07% coefficients unchanged during evaluation.

**Independent betting/value controls are essential:** Since ~83% of the Test C probability originates from the bookmaker itself, the blend must **not** be naively fed into same-book implied-odds-vs-model value calculations; this can generate misleading mathematical confidence about betting edges. Saturday Forecast's six waterfall tiers independently use spread/moneyline rules, opponent metrics and custom conditions. Simply changing predicted winners/labels risks inconsistent tier picks, explanations and high-confidence warnings unless those separately tested systems are reconciled. Historical winner superiority does not establish better ATS or betting return.

**No production prediction, value-pick logic, confidence labels or tier calculations were modified.**

## Reproduce and audit

- `research/test_c_blend_2024_2025.py`: fixed-weight full-season comparison with strict source matching, missing-price fallback, season/week splits, sensitivity and cluster bootstrap.
- `research/test_c_blend_2024_2025_results.json`: exact numerical evidence.
- `research/test_c_blend_2024_2025_games.csv`: per-game primary opening-odds comparison.
- `.github/workflows/test-c-historical-blend-2024-2025.yml`: completed reproducible Actions research run.

References: [Historical odds archive validation](https://github.com/christianmellis1-debug/CFB_Prediction_app/blob/research/test-c-external-validation-2026-10-13/research/TEST_C_HISTORICAL_VALIDATION.md), [Current leading shadow model specification](https://github.com/christianmellis1-debug/CFB_Prediction_app/blob/main/research/TEST_C_LEADING_CHALLENGER.md), [Week 3–6 2026 matched head-to-head](https://github.com/christianmellis1-debug/CFB_Prediction_app/blob/research/test-c-head-to-head-weeks3-6-2026-10-13/research/TEST_C_V15_WEEKS3_6_REPORT.md).
