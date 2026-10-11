# V1.5 main-weight sensitivity — October 11, 2026

**Status:** Research only. No live model or selection rules changed.

## Design
Tested 23 prespecified weighting configurations using the production V1.5 scoring calculation and earlier-week advanced statistics, regular-season FBS games, 2024 (752 games), 2025 (762), and completed 2026 Weeks 1–6 (329). Held conference log-odds adjustment and probability calibration fixed. Candidate selection by 2024 Brier, using 2025 and 2026 to assess robustness; note these seasons have been previously inspected and are not pristine unseen holdouts.

Verified numerical parity with the production probability function in Weeks 2, 5 and 6 of all three seasons, maximum absolute difference approximately 3.33e-16.

## Results

| Main weights (off/def/venue/SOS) | 2024 accuracy | 2025 accuracy | 2026 W1–6 accuracy | 2024 Brier | 2025 Brier | 2026 Brier |
|---|---:|---:|---:|---:|---:|---:|
| 35/35/20/10 (baseline) | 71.41% | 71.65% | 73.25% | .187816 | .182967 | .170812 |
| 30/30/30/10 | 70.35% | 71.78% | 74.16% | .187323 | .182383 | .169840 |
| 40/30/20/10 | 71.14% | 71.92% | 72.64% | .187350 | .183827 | .169082 |
| 40/40/20/0 | 71.68% | 72.97% | 72.34% | .189310 | .183544 | .172830 |
| Same baseline, current-season weight +10pp | 71.68% | 71.00% | 73.86% | .187219 | .184512 | .173720 |

Lower Brier is better. No alternate configuration consistently improves both accuracy and Brier in all three seasons.

## Week 6 diagnostic

The completed-game retrospective Week 6 cohort includes 58 games; this differs from the 56-game immutable forward-test cohort because they have different coverage and capture rules, and retrospective feed revisions may change predictions.

- V1.5 baseline: 37–21 (63.79%), Brier .22132.
- 30/30/30/10: 35–23 (60.34%), Brier .22299.
- 35/35/10/20: 40–18 (68.97%), Brier .21819, but not reliably superior across seasons.
- 45/25/20/10: 39–19 (67.24%), Brier .21388, but 2025 accuracy falls below baseline.

Optimizing solely on one bad week risks overfitting.

## Conclusion

Retain the current production model unchanged. Explore within-unit measures (adjusted EPA, success, explosive plays, red zone) under predeclared modest variants and assess the next prospective frozen cohort before considering any model replacement. Historical data cannot prove a change will improve future accuracy. No claims about ATS performance or betting ROI follow from straight-up winner accuracy alone.

Machine-readable results and changed-winner samples: results.json. Re-run: PYTHONPATH=. python research/weight_sensitivity_2026_10_11/run.py.
