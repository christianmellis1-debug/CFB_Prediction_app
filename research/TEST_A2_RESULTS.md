# Test A2 — three-game opponent-adjusted offensive and defensive EPA

**Research only, isolated from production.** Completed October 13, 2026.
No changes to `model_v1_5.py`, the deployed Streamlit app, or the value waterfall.

## Method

- Source: SportsDataverse weekly cumulative team summaries and FBS schedules, 2023–2026.
- Compute each game's raw offensive and defensive EPA from the differences in cumulative total EPA and cumulative play counts for that team. Require at least 15 and at most 160 qualifying plays in each unit; require one eligible FBS game for the team in that schedule week.
- Adjust each game: offense = own raw offensive EPA minus opposing defense's **pregame** adjusted defensive EPA; defense = own raw defensive EPA allowed minus opposing offense's **pregame** adjusted offensive EPA. If no earlier-week opponent rating is available, use the previous season's final rating. Exclude that game when neither is available.
- For each team with at least four eligible prior games, calculate weighted (by unit plays) last-three EPA minus weighted all-prior-games EPA, separately for offensive and defensive ratings. Standardize within the target-week cross-section and clip to ±2.5.
- Evaluate adjusted offense-only, adjusted defense-only, both, and unadjusted both at multipliers 0.10, 0.20, 0.35 and 0.50, layered as additive contributions to the baseline home-win log odds.
- Evaluate the baseline and each challenger on **identical matchups**. The baseline is the current V1.5 code reconstructed for historical 2024–2025 games; for 2026 use the original locked pre-kickoff V1.5 probabilities from `data/shadow_tracking.json`. This is a retrospective challenger evaluation, **not** frozen challenger predictions from 2026.
- Use 2024 Brier score to choose the challenger. Evaluate it unchanged on 2025 and 2026. The historical source data may have been revised after games and those years were used in other model development, so 2025 is not a pristine model-wide holdout.

## Selected challenger

**Opponent-adjusted offensive EPA recent-form only, weight 0.20**, selected on 2024 Brier score.

| Season | Same-game baseline | Test A2 selection | Baseline Brier | Test A2 Brier | Eligible signals |
|---|---:|---:|---:|---:|---:|
| 2024 | 394–163 (70.7%) | 396–161 (71.1%) | 0.193873 | 0.192665 | 370 / 557 |
| 2025 | 406–160 (71.7%) | 407–159 (71.9%) | 0.184524 | 0.183996 | 386 / 566 |
| 2026 Weeks 5–6 | 77–35 (68.8%) | 77–35 (68.8%) | 0.208983 | 0.207801 | 4 / 112 |

**Total 2024–2025:** baseline 800/1,123, selected 803/1,123. Net three additional correct winners, small relative to sample size; not reliable proof of uplift. The 2026 Brier improvement comes from only four affected matchups.

**2026 restrictions:** no Week 5 matchups qualified because no team pair had at least four usable prior opponent-adjusted FBS games; four Week 6 matchups qualified. The selected challenger did not flip any Week 5 or Week 6 winner. Against USC, Penn State's home-win probability declined from 80.2% to roughly 75.1%, but the wrong winner stayed unchanged. This cannot explain or repair last weekend's overall slump.

**Comparison of 0.20 adjusted variants:**

| Variant | 2024 wins / 557 | 2025 wins / 566 |
|---|---:|---:|
| V1.5 baseline | 394 | 406 |
| Recent adjusted offense | 396 | 407 |
| Recent adjusted defense | 386 | 409 |
| Both recent adjusted units | 390 | 413 |

Defense shows inconsistent season-to-season results, which is a reason not to increase its weight based on the recent weekend alone.

## Limitations and decision

The adjusted residual is a pregame-opponent-strength heuristic, **not** a per-game re-fit of the original ridge EPA adjustment. Differencing weekly cumulative summary totals can be affected by later source revisions and by source coverage of non-FBS games. Game-level histories are restricted to FBS opponents, but exact isolation of play-by-play from excluded FCS contests has **not** been independently verified. The baseline current-season V1.5 predictions for 2024–2025 are retrospective reconstructions, unlike the 2026 archived probabilities.

The strict four-game minimum makes this mostly a mid/late-season idea; it is insufficient for Week 5–6 2026 model improvement. A substantial change should require more historical cohorts, verified play-by-play or event-level EPA, consistent improvements to accuracy and calibration, and prospective capture. Retain the selected offense adjustment **as a challenger only**, not the official prediction model.

## Files

- `research/test_a_recent_epa.py`: reproducible analysis.
- `research/test_a_recent_epa_results.json`: all candidate weights and same-game summary metrics, coverage and hashes.
- `research/test_a_recent_epa_game_results.csv`: per-game baseline probability and computed independent adjustment signals.
- Workflow: `.github/workflows/research-test-a2-epa.yml` on the research branch.

Data source documentation: https://cfbfastr.sportsdataverse.org/reference/load_espn_cfb_team_summaries.html
