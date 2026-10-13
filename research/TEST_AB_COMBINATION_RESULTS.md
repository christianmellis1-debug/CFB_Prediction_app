# Saturday Forecast — Combined Test A + B Research

**October 13, 2026. Research only; no change to production V1.5, Streamlit application, betting tiers or value shortlist.**

## Compared variations

This is a same-game comparison that joins Test A's `shift_adjusted_offense` and Test B's `elo_hfa4` versus `raw` venue signals using `season/year` and `game_id`. All 1,235 available Test A records align uniquely with the 1,626 Test B records. The baseline probabilities and outcomes agree exactly across the overlapping samples.

- **Baseline:** existing V1.5 probabilities, reconstructed for 2024–2025 and frozen pregame predictions for Week 5–6 in 2026.
- **A only:** adjust baseline log odds by 0.20 × the recent, opponent-adjusted offensive EPA deviation, when available.
- **B only:** replace the venue term's raw historical home-road margin with the opponent-strength-adjusted venue margin plus its exploratory four-point generic home advantage, retaining venue coefficient 0.20. The replacement is applied as a delta to existing baseline log odds, not a second venue contribution.
- **A+B additive:** add both independent log-odds deltas.
- **Conditional alternative:** when Test A's strictly pregame EPA recent-form signal is eligible, apply **A only** (leave V1.5's original venue term untouched); otherwise apply **B only**.

These are fixed coefficients inherited from the separate experiments and were not refitted in this combined comparison. **Crucially, the conditional switching idea was devised after examining earlier results**, and is therefore post-hoc across *all three seasons*. It is not a clean independent 2025 or 2026 holdout. Prospective validation is required.

## Accuracy results

| Variant | 2024 W–L / 752 | 2025 W–L / 762 | Archived 2026 W–L / 112 | Pooled W–L / 1626 |
|---|---:|---:|---:|---:|
| V1.5 baseline | 536–216 | 546–216 | 77–35 | 1159–467 |
| A only | 538–214 | 547–215 | 77–35 | 1162–464 |
| B only | 544–208 | 544–218 | 79–33 | 1167–459 |
| Full A+B | 538–214 | 547–215 | 79–33 | 1164–462 |
| **Conditional A or B** | **543–209** | **549–213** | **79–33** | **1171–455** |

The conditional approach is +7 winners in 2024, +3 in 2025, +2 in the 2026 frozen baseline sample, net +12 winners out of 1,626 games. This is approximately 72.02% versus 71.28% baseline. The improvement is small and likely overestimated due to post-hoc exploration.

## Probability scoring (Brier; lower is better)

| Variant | 2024 | 2025 | 2026 |
|---|---:|---:|---:|
| Baseline | 0.187913 | 0.183029 | 0.208983 |
| A only | 0.187018 | 0.182636 | 0.207801 |
| B only | 0.187159 | 0.184659 | 0.207090 |
| Full A+B | 0.186403 | 0.184422 | 0.205927 |
| **Conditional** | **0.186393** | **0.182138** | **0.206232** |

Full A+B has slightly better Brier in 2024 and 2026, but worse in 2025. Conditional has lower Brier than baseline in each of the three seasons, although chosen after viewing those results.

## Coverage and recent weekend

Test A's strict recent EPA rule was eligible for 370 of 752 games in 2024, 386 of 762 in 2025, and **only four of 112 frozen 2026 games**. Conditional uses B on all other games.

- **2026 Week 5:** Baseline 42–14; conditional 45–11, three corrected predictions.
- **2026 Week 6:** Baseline 35–21; conditional 34–22, one newly wrong prediction.
- Conditional 2026 changes are the same four as B: correctly switches to Air Force against Navy, Kentucky against South Carolina, San Diego State against Texas State; incorrectly switches to Temple against UConn.

Despite a better combined headline percentage, **the conditional test does not solve the last-weekend Week 6 weakness**.

## Why conditional beats naïve addition

The corrections are not independent. In the subset where both Test A and B can apply, naively adding both log-odds adjustments can push marginal predictions across the 50% line in the wrong direction. The conditional approach avoids those simultaneous flips, allowing A to replace B when enough early-week observations exist.

This does **not** establish a causal benefit or reliable superiority; there is substantial selection bias from comparing alternatives on already-seen historical labels.

## Important limitations

- V1.5's 2024 and 2025 probabilities are retrospective reconstructions based on currently published stats; the 2026 baseline comes from locked pre-kickoff snapshots, and all new challengers are calculated retrospectively.
- Previous analysis used these seasons, so the conditional formula was not prospectively registered or independently held out.
- Test A's opponent-adjusted EPA residual is a heuristic computed from differences in cumulative weekly EPA and may be affected by source revisions or non-FBS play coverage; the strict four-prior-game requirement sharply limits early-season usage.
- Test B's Elo margin normalization (25 Elo points per point), 2.5 point removal in historical residual, and four-point reintroduction are heuristic, not jointly calibrated.
- Accuracy improvement of +12/1626 is not substantial statistical evidence and should **not** be interpreted as a confidence guarantee or a betting-return improvement.
- Keep betting tiers/value selections unchanged until a prospective head-to-head experiment supports a change.

## Recommended next step

Freeze the **conditional A/B** configuration as a *shadow challenger*, capture its pre-kickoff probabilities and matchup eligibility alongside official V1.5 (on the same games), then compare for several weeks. Evaluate overall SU accuracy, Brier score, Week 5–8 results, confidence calibration, and performance in bookmaker disagreements. Keep official V1.5 and all existing waterfall tiers unchanged meanwhile.

## Source and reproduction

- Test A files: [research branch](https://github.com/christianmellis1-debug/CFB_Prediction_app/tree/research/test-a-three-game-epa-2026-10-13/research).
- Test B files: [research branch](https://github.com/christianmellis1-debug/CFB_Prediction_app/tree/research/test-b-venue-calibration-2026-10-13/research).
- Joined comparison: `research/test_ab_combination.py`, with source CSVs pinned to published research commits.
- Numerical evidence: `research/test_ab_combination_results.json`, generated independently by the branch workflow.
