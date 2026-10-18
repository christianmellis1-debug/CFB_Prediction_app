# Tier 1 six-of-six vs five-of-six vs four-of-six controlled study

**2026-10-18 | research only | production unchanged**

## Core question

Does the six-of-six rule (home field plus 5 of 5 favorable pregame statistical metrics) improve home-side ATS results compared with 5/6 or 4/6, beyond the spread, pregame Elo gap, and conference context?

## Data and methodology

- Reconstructed 2024, 2025 and 2026 completed same-group FBS regular-season nonneutral games.
- Original production matchup routine `build_advantages` and `assess`; earlier-week box-score data only; 4/6=3 favorable statistical metrics plus home, 5/6=4 plus home, 6/6=5 plus home.
- ESPN-derived archived home point spreads, FBS schedule final scores and pregame team Elo ratings.
- Counted **home ATS results** irrespective of whether the home team was favored and irrespective of whether another tier in the app would have claimed the game first.
- 2024: 291 qualified games with valid spreads, 2 missing spreads; 2025: 276; 2026: 119. Total 686 (4/5/6).
- This is retrospective reconstruction, not a time-stamped historical wager ledger. The 2026 6/6 reconstruction (33 total; 18–15) differs from earlier production reconstructed/archived 31-pick, 17–14 Tier 1 because it includes games regardless of other waterfall tier priority and captures the historical feed's own market quotes. Don't equate the cohorts.
- Run: [GitHub Actions 39139000726](https://github.com/christianmellis1-debug/CFB_Prediction_app/actions/runs/39139000726); research-specific test passed, broader suite still had four unrelated existing UI/copy test failures. Production branch unaffected.

## Raw yearly home ATS results

| Count | 2024 | 2025 | 2026 | Combined |
|---|---|---|---|---|
| 4/6 | 68–47 (59.1%) | 52–58 (47.3%) | 26–22–3 (54.2%) | **146–127–3 (53.5%)** |
| 5/6 | 42–53 (44.2%) | 44–44 (50.0%) | 16–19 (45.7%) | **102–116 (46.8%)** |
| 6/6 | 40–41 (49.4%) | 43–35 (55.1%) | 18–15 (54.5%) | **101–91 (52.6%)** |

For 6/6 versus pooled 4/5, raw ATS win-rate advantage approximately +2.1 percentage points; year-stratified row bootstrap (3000 resamples, imperfect team/season dependence) percentile interval **[-6.1, +10.2] percentage points**.

## Confounding

| Count | Mean |spread| | Mean home pregame Elo advantage | Home favored fraction |
|---|---:|---:|---:|
| 4/6 | 8.09 | +66.9 | 73.6% |
| 5/6 | 9.50 | +149.6 | 87.2% |
| 6/6 | 14.91 | +293.2 | 94.3% |

Six-of-six teams are stronger and overwhelmingly home favorites; betting lines price in the mismatch. A simple monotonic relationship between the number of edges and chance of covering is not supported.

## Comparable spread buckets (all years)

| Home spread category | 4/6 | 5/6 | 6/6 |
|---|---|---|---|
| Home underdog | 47–25–1 (65.3%) | 16–12 (57.1%) | 6–5 (54.5%) |
| 0 to -3 | 17–13–1 (56.7%) | 9–15 (37.5%) | 7–5 (58.3%) |
| -3.5 to -6.5 | 31–26 (54.4%) | 19–28 (40.4%) | 14–15 (48.3%) |
| -7 to -13.5 | 38–39–1 (49.4%) | 34–28 (54.8%) | 19–20 (48.7%) |
| -14 to -20.5 | 7–17 (29.2%) | 19–23 (45.2%) | 29–22 (56.9%) |
| -21 or more | 6–7 (46.2%) | 5–10 (33.3%) | 26–24 (52.0%) |

The 6/6 vs 4/5 signal is relatively more pronounced in the -14 to -20.5 category, but these are *post hoc* subgroup observations, not validated selection rules; team strengths within each spread bucket still vary. The 2026 six-of-six "Prime Only" streak does not generalize across 2024–25.

## Matched analysis

Restricted to overlap in season, spread bucket, pregame Elo bin (<0, 0–149, 150–299, 300+), P4/G6. Includes 185/192 six-of-six matches in comparable cells. Weighted matched observed six-of-six ATS rate: 53.51%; historical controls weighted to six-of-six distribution: 46.29%; difference **+7.22 percentage points**, BUT some cells have only 3–8 controls, and no cluster-aware confidence interval. This is a fragile descriptive signal and does not establish causal incremental value.

## Out-of-year incremental predictive signal

Logistic ATS model baseline predictors: absolute home spread, home-favorite indicator, pregame Elo advantage (per 100 points), P4 group and week. Augmented model adds indicators for five-of-six and six-of-six (4/6 comparison category). L2 regularization. Evaluated on untouched later years.

| Holdout | Games | Baseline Brier | Add advantage count Brier | Delta (negative better) |
|---|---:|---:|---:|---:|
| Fit 2024; test 2025 | 276 | 0.25219 | 0.25597 | **+0.00378 (worse)** |
| Fit 2024+2025; test 2026 | 116 (pushes excluded) | 0.25427 | 0.25253 | **-0.00174 (better)** |

Both models did worse than a flat 0.2500 probability benchmark in both holdouts. Adding the advantage-count indicators did not produce a durable gain in predictive quality across seasons. There is no robust case to require 6/6 specifically for all spreads.

## Recommendations

1. **Do not change production Tier 1 advantage requirement or create 4/6 or 5/6 tiers solely from these findings.** More/statistical-advantage count is not a stable ATS advantage.
2. Freeze the current market-aware Elo spread-value challenger as *research*, not deployment-ready; benchmark it prospectively before adopting.
3. Next predeclared hypothesis: test six-of-six specifically for home favorites -14 to -20.5 across held-out weeks and compare with controls of matching Elo and spread, and separately investigate 4/6 home underdogs (47–25–1) for selection robustness. Avoid converting either exploratory subgroup to a new tier without validation.
4. Audit redundancy/edge magnitudes in the five core statistics; treating tiny highly-correlated advantages equally may explain why 6/6 is not progressively predictive.

No production code was modified. The research branch is retained for reproducibility.
