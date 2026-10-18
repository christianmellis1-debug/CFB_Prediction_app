# Tier 1: Controlled 4/6 vs 5/6 vs 6/6 comparison (2026-10-18)

**Outcome: No compelling evidence that a strict 6/6 selection is a reliable ATS edge.** Research-only, no production modifications.

## Definition and source
Each home team has a guaranteed home-field advantage (1 of 6) plus either 3, 4 or 5 of the five pregame statistical advantages defined in production `matchup_advantages.build_advantages`. Therefore 4/6 = 3 statistical edges; 5/6 = 4; 6/6 = all five. Only same-group P4/P4 or G6/G6, nonneutral, final FBS games, using previous-week statistics and archived ESPN-derived home spreads. Archived lines are not always actual pregame-locked prices.

2024: 2 home game quotes missing out of 571 scored eligible games; 2025 and 2026: none missing. For 4–6 advantage comparison, 2024 n=291, 2025 n=276, 2026 n=119 (2026 includes three 4/6 spread pushes).

## Historical ATS records

| Year | 4/6 | 5/6 | 6/6 |
|---|---|---|---|
| 2024 | 68-47 (59.1%) | 42-53 (44.2%) | 40-41 (49.4%) |
| 2025 | 52-58 (47.3%) | 44-44 (50.0%) | 43-35 (55.1%) |
| 2026 through Week 7 | 26-22-3 (54.2% ex pushes) | 16-19 (45.7%) | 18-15 (54.5%) |
| **All three** | **146-127-3 (53.5%)** | **102-116 (46.8%)** | **101-91 (52.6%)** |

The historical 2026 raw 6/6 study cohort is 33 home six-of-six qualifiers, not the same as the separately preserved 31 official/reconstructed waterfall Tier1 bet selections; do not mix the 18-15 6/6-only scope with the 17-14 official+reconstructed Tier1 scope.

Average home relative sportsbook spread across all three years: 4/6 -5.24, 5/6 -8.62, 6/6 -14.53. Average pregame home Elo advantage: 4/6 +67, 5/6 +150, 6/6 +293. That is material case-mix confounding: six-of-six teams generally face much higher ATS hurdles.

## Market-/Elo-/group-controlled comparisons

A descriptive fixed-stratum analysis, matching spread bands, pregame Elo bins and P4/G6 group, standardized to the 6/6 game distribution, found:
- 2024+2025 6/6 vs 5/6: +6.37 percentage points, with 156/159 six-of-six games in overlapping bins.
- 2024+2025 6/6 vs 4/6: +11.00 points, with 159/159 overlapping.
- 2026 6/6 vs 5/6: +11.01 points, with 28/33 overlapping.
- 2026 6/6 vs 4/6: **-11.11** points, with 27/33 overlapping.
- Across all seasons 6/6 vs 5/6: +7.97 points, 188/192 overlapping.
- Across all seasons 6/6 vs 4/6: +8.78 points, 192/192 overlapping.

These descriptive contrasts can be noisy or depend on sparse comparator cells. An independent season+group+spread+Elo controlled standardization in the same research workflow found a pooled 6/6 vs combined 4/6 and 5/6 contrast of +7.22 percentage points on 185/192 overlapping six-of-six games. These are **associations**; neither implies genuine future sportsbook outperformance.

## Incremental holdout test

A ridge-regularized logistic home-ATS model using market spread, absolute spread, pregame Elo gap, absolute Elo gap, and P4 group was compared head-to-head with the same model **plus 5/6 and 6/6 advantage count indicators**. Parameters fitted only on prior seasons.

| Season holdout | 50% baseline Brier | Spread/Elo controls only | Controls + advantage count | Change |
|---|---:|---:|---:|---:|
| 2025 (trained 2024) | 0.25000 | **0.25589** | 0.25895 | +0.00305, worse |
| 2026 (trained 2024–2025) | **0.25000** | 0.25402 | 0.25295 | -0.00107, modestly better |

The advantage count helped the 2026 holdout slightly relative to a control-only model, but worsened the 2025 holdout and both models fell short of the simple 50% Brier baseline. The training logistic coefficient suggested 6/6 vs 5/6 adjusted cover odds ratio ~1.34 (2024 training) and ~1.33 (2024+2025), an exploratory conditional association not a validated advantage.

## Recommendation

Do not change existing Tier 1 logic solely by replacing 6/6 with 5/6 or 4/6, nor claim 6/6 independently guarantees value. The market prices the statistical and Elo dominance into larger required cover margins. Keep 6/6 as a descriptive matchup flag while researching genuine **independent spread value**, and prospectively freeze new selection and market prices for a clean 2026 remainder-of-season test. Explicitly compare Brier/calibration and flat-stake ROI on pregame snapshots before deployment.

Standalone study: `tests/test_tier1_4v5v6_controlled.py`. CI research run 39140156116: study test itself passes; pre-existing stale app-UI copy assertions still fail the broad suite. No production app/model changes.
