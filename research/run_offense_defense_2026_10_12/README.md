# Run-first offensive and defensive model research

**Research-only. No changes to production model V1.5, value tiers, or the existing four-model prospective archive.**

Tested 33 prespecified variants across 2022–2026, with independent earlier-week rushing production (yards per attempt) and rushing defense (opponent yards allowed per attempt). Rushing features are standardized separately across available FBS teams; incomplete and ambiguous two-sided box scores do not contribute. Other V1.5 coefficients, season blending, prior Elo/efficiency, home/away term, strength of schedule, conference adjustment and sigmoid remain unchanged. Changes affect only current-season internal offense or defense ratings. Retrospective summaries may have been revised.

In each EPA-only candidate, success rate is zero; in success-only candidates, EPA is zero. A control retains both alongside rushing. Offense-only, defense-only and several asymmetric two-unit versions are tested.

## Main results

| Model | 2024 wins/661 | 2025 wins/663 | 2026 wins/228 | 2024 Brier | 2025 Brier | 2026 Brier |
|---|---:|---:|---:|---:|---:|---:|
| V1.5 original | 471 | 474 | 164 | .188955 | .185770 | .180809 |
| Defense 45 EPA / 0 success / 20 explosive / 15 red-zone / 20 run | 468 | 476 | 167 | .188455 | .185333 | .181404 |
| Defense 30 EPA / 25 success / 10 explosive / 10 red-zone / 25 run | 468 | 482 | 164 | .188769 | .185381 | .179346 |
| Offense 45 EPA / 0 success / 20 explosive / 15 red-zone / 20 run | 467 | 472 | 166 | .189967 | .186824 | .181863 |
| Both units 45 EPA / 0 success / 20 explosive / 15 red-zone / 20 run | 461 | 475 | 165 | .189425 | .186038 | .182367 |

2022: 634 eligible games, 2023: 651, 2024: 661, 2025: 663, 2026 Weeks 3-6: 228. All candidates evaluated on the same year-specific cohort.

The defense-25%-rushing option that retains EPA and success has lower Brier score than baseline in **all five seasons**, but straight-up accuracy is not uniformly better. Forcing removal of EPA or success in both offense and defense does not clearly improve generalization.

## Rushing advantage standalone descriptive records

| Season | Stronger rushing offense wins | Stronger run defense wins | Both advantages on same team |
|---|---:|---:|---:|
| 2022 | 376/634 | 383/634 | 236/347 |
| 2023 | 397/651 | 405/651 | 252/353 |
| 2024 | 434/661 | 410/661 | 291/399 |
| 2025 | 407/663 | 392/663 | 245/354 |
| 2026 Weeks 3-6 | 138/228 | 144/228 | 89/124 |

These are unconditional associations, not causal estimates or betting strategies. Run YPC is not opponent-adjusted; team quality, market favorite status and schedule can explain some apparent edge. These rates do not establish added value beyond V1.5 without same-game head-to-head evaluation.

## Proposed next prospective challenger set

Compare against the unchanged V1.5 baseline: (1) defense EPA 45, run 20, success 0; (2) defense EPA 30, success 25, run 25; (3) offense and defense EPA 45, success 0, run 20. Do not select a permanent model on a single bad week or retroactively rewrite frozen predictions. Test additional opponent-adjusted rushing offense-vs-run defense matchups as an independent hypothesis.

Full numerical results in results.json; reproducible code in run.py. Four additional regression checks in tests/test_rush_weight_research.py. No changes were made to the live Streamlit prediction engine.
