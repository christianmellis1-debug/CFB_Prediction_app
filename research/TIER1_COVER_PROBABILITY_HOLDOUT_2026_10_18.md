# Tier 1 cover-probability calibration: 2024–2026 historical holdouts

**Completed 2026-10-18. No production changes.** This report accompanies the research-only test `tests/test_tier1_cover_probability_historical.py`, which passed independently in [GitHub Actions run 39137827121](https://github.com/christianmellis1-debug/CFB_Prediction_app/actions/runs/39137827121). Other existing regression tests retain unrelated UI/copy failures.

## Design

Test existing six-statistical-advantage Tier 1 home picks against a market-neutral 50% ATS baseline. Fit projected-margin models on 2024 data and evaluate on 2025; refit on 2024–2025 and evaluate on 2026. A minimum two prior verified FBS games per team is required. Opponents' pregame Elo ratings are measured *as of those earlier games*; current and future weeks never enter features.

Convert independent margin projections (Elo-only, raw historical scoring, opponent-strength-adjusted scoring) into cover probabilities with a normal error model whose standard deviation is estimated from earlier-year residuals. Fit an additional regularized logistic calibration using historical Tier 1 candidates; the 2025 candidate sample is projected using the 2024 model. The logistic calibration uses **in-sample 2024 predicted margins**, which could make that branch optimistic. Calibration bands, Brier scores and log loss are reported without ROI claims or betting guarantees.

2025 contains 75/78 reconstructed Tier 1 qualifiers with sufficient earlier FBS history. 2026 contains 30/33 reconstructed qualifiers. Locked October 17 Week 7 has all 10 selections. Market spreads prior to that locked archive are archived ESPN-derived and may differ from real-time pregame prices.

## Cover-probability Brier scores (lower is better)

| Evaluation | 50% market-neutral baseline | Elo only | Raw scoring | Opponent-adjusted | Regularized logistic |
|---|---:|---:|---:|---:|---:|
| 2025 held out (75 Tier 1 picks) | **0.25000** | 0.27463 | 0.27796 | 0.27298 | 0.25289 |
| 2026 held out (30 Tier 1 picks) | 0.25000 | **0.24297** | 0.24545 | 0.24654 | 0.24914 |
| Locked 2026 Week 7 (10 picks) | 0.25000 | **0.23303** | 0.24924 | 0.24648 | 0.26421 |

On 2025, all tested probability models performed worse than the 50%-cover baseline. 2026 improvements were modest, with Elo-only the best performer; opponent-adjustment did *not* improve the cover Brier score over plain Elo.

## Selection cohorts

2025 Tier 1 eligible baseline **42–33 (56.0%)**; normal Elo P(cover) >=50% **13–16 (44.8%)**; >=55% **11–11 (50.0%)**; opponent-adjusted >=55% **7–11 (38.9%)**.

2026 Tier 1 eligible baseline **16–14 (53.3%)**; normal Elo P(cover)>=50% **9–6 (60.0%)**, >=52.5% **9–4 (69.2%)**, >=55% **8–4 (66.7%)**. Opponent-adjusted >=50% **10–6 (62.5%)**, >=55% **9–5 (64.3%)**.

Locked October 17 baseline **3–7 (30.0%)**; Elo P(cover)>=50% **2–2 (50%)**, opponent-adjusted >=50% **2–2 (50%)**; opponent-adjusted >=60% **0–1**. The logistic calibration assigned nearly identical probability (~53.2%) to all ten and did not identify a useful subset.

## Interpretation

The original 2026 margin-vs-spread filter remains the best *exploratory* candidate seen within 2026, with reconstructed + archived 2026 Week 3–7 picks 11–6 (64.7%) vs 17–14 (54.8%). But a similar walk-forward Elo margin-vs-spread filter selected 13–16 in 2025, below its 42–33 baseline. Hence it lacks historical replication.

A normal-error cover probability is a monotonic transformation of the margin-vs-spread edge; it changes thresholds and presentation, not the underlying game ranking. Regularized logistic calibration to Tier 1 historical results did not reveal a persistent predictive link between projected margin edges and ATS cover probabilities. Two major 2026 locked mistakes (Duke -3 and Bowling Green -6.5) retained elevated estimated cover probabilities.

**Recommendation:** Keep all probability and spread-value candidate logic research-only; do not describe 60%+ projected cover chances as calibrated or deploy it as an official tier. Next rigorous test should estimate game-specific margin uncertainty and probabilities using an untouched forward capture of recommendations, benchmark against 50% ATS and ~52.4% betting break-even at -110, and avoid multiple post-hoc thresholds. An alternate hypothesis is that the current 6/6 criterion has weak incremental signal beyond sportsbook prices; test its opponents and side-specific results before upgrading Tier 1.

Test code: `tests/test_tier1_cover_probability_historical.py`. Main branch was not modified.
