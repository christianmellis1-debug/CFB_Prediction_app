# Saturday Forecast — Test D Part 1: Early-season weighting and incomplete statistics

**October 13, 2026. Research-only.** The newly promoted Test C primary prediction blend, independent V1.5 engine, historical records and six waterfall tiers remain unchanged.

## Hypothesis and experimental design

**Does V1.5 underperform when teams have little or no historical advanced data, and can early-season weights or sensible missing-data fallbacks improve both V1.5 and the new Test C blended prediction?**

The current V1.5 mixes preseason profile with current-year advanced metrics using a weekly scalar: **Week 1 30%, Week 2 40%, Week 3 50%, Week 4 60%, Week 5 65%, Week 6 70%** current season. When a team has no previous-week current-season profile, `model_v1_5._latest_snapshot` returns a zero-valued three-factor vector. This is an explicit null-data fallback, not a missingness flag.

Reconstructed **2024 295 games**, **2025 296 games**, and **2026 329 games** from completed FBS Weeks 1–6, using only eligible pregame-week cumulative statistics. Seven configurations including baseline:

- **Baseline V1.5:** current weekly weights and zero-valued missing-snapshot fallback.
- **Conservative −10:** reduce current-season scalar by 0.10 in Weeks 1–6 (e.g. Week 5 .65→.55).
- **Conservative −20:** reduce by 0.20.
- **Half current-season:** 50% of current scalar.
- **Aggressive +10:** increase the current scalar by 0.10.
- **Retain prior if no current profile:** use the established preseason profile for a team with no eligible previous-week statistical snapshot, instead of treating current metrics as zero.
- **Conservative −10 + prior fallback** combined.

The **minimum 2024 Weeks 1–6 Brier** selects the challenger, with no re-tuning on 2025 or 2026. Current-season adjusted/raw EPA and success metrics are not refitted in these tests; models otherwise use identical existing calibrated V1.5 components and conference corrections. All 2024–2025 predictions are retrospective recalculations from presently published weekly summaries, not locked originally pregame forecasts.

For the **112 archived 2026 Weeks 5–6** observations, use original frozen V1.5 pregame probabilities for the baseline. Candidate changes in log odds are reconstructed and added to those frozen baselines; they are **retrospective sensitivity proxies, not truly frozen modified-model forecasts**. The other 2026 Weeks 1–4 and the two non-archived Week 6 games are retrospective reconstructions. Results from those two provenance classes are not silently pooled in conclusions about original 2026 forecasts.

## D1 — Historical V1.5 winner results

| Same-game baseline/alternative | 2024 W–L / 295 | 2025 W–L / 296 | Frozen W5–6 2026 W–L / 112 |
|---|---:|---:|---:|
| **V1.5 baseline** | **211–84** | **209–87** | **77–35** |
| Conservative −10 | 213–82 | 210–86 | 77–35 |
| Conservative −20 | 210–85 | 210–86 | 75–37 |
| Half current-season weight | 204–91 | 210–86 | 74–38 |
| Aggressive +10 | 212–83 | 208–88 | 75–37 |
| Prior profile instead of zero on missing snapshot | 211–84 | **211–85** | 77–35 |
| Conservative −10 plus prior fallback | 213–82 | 210–86 | 77–35 |

**The minimum-2024-Brier selection was +10** (2024 Brier **0.177677** vs V1.5 **0.179832**), but its Brier and accuracy **worsened** in 2025 (**0.184104 vs 0.184023**, one fewer winner) and the frozen 2026 cohort (**0.212183 vs 0.208983**, two fewer winners). Thus the 2024-selected early-season alternative **fails replication**.

Conservative −10 improved 2024 winner accuracy by two, 2025 by one, and matched frozen 2026, but was **less calibrated** in 2024 (Brier 0.183151 vs 0.179832) and 2025 (0.185180 vs 0.184023). The archived 2026 Brier improved slightly (0.207327 vs 0.208983), but these are retrospective changes to a frozen baseline.

The no-snapshot prior substitution fixed two 2025 predictions (211–85), but increased Brier (0.185547 vs 0.184023) and left the 112 frozen Weeks 5–6 predictions unchanged.

## D2 — Does missing information actually predict errors?

| Season Weeks 1–6 | Games with either team's latest eligible team-summary missing | V1.5 correct | Accuracy |
|---|---:|---:|---:|
| 2024 | 84 / 295 | 62–22 | 73.8% |
| 2025 | 83 / 296 | 59–24 | 71.1% |
| 2026 | 88 / 329 | 73–15 | **83.0%** |

In this dataset, games with at least one missing prior-week summary do **not** consistently have lower raw winner accuracy than other games. This likely reflects opponent and week selection (e.g. early mismatches), not a conclusion that missing data are unimportant. A missingness indicator is not causal evidence that the fallback algorithm is working optimally.

Crucially, **all 112 archived 2026 Weeks 5–6 matchups had an eligible prior-week snapshot for both teams** and at least two previous FBS games each. The no-snapshot correction therefore couldn't possibly fix the decline in Week 6, and its unchanged result on these games is expected.

Adjusted EPA columns alone were missing in 158/295 (2024), 155/296 (2025), and 153/329 (2026). V1.5 already uses raw EPA fallback for adjusted EPA when available; these games aren't equivalent to having zero team information. Test D Part 1 did **not** prove that specific fallback is optimal; that requires a separate same-team raw-versus-adjusted reliability test.

## D3 — Effect on the newly promoted Test C blend

Maintain the frozen `P_TestC = 0.16927926947215113 × P_V1.5 + 0.83072073052784887 × P_market`. Assess all V1.5 variants on exactly matched market-priced games, **not** revised blend weights:

- 2024 Weeks 1–6: **263 matched ESPN BET opening-quote games**.
- 2025 Weeks 1–6: **269 matched ESPN BET opening-quote games**.
- 2026 frozen Weeks 5–6: **112 pregame same-book snapshot games**, using reconstructed variant effects on frozen V1.5.

| V1.5 input to fixed Test C | Test C 2024 / 263 | Test C 2025 / 269 | Test C frozen 2026 / 112 |
|---|---:|---:|---:|
| **Original V1.5** | **190–73** | 199–70 | **78–34** |
| Conservative −10 | 189–74 | **200–69** | **78–34** |
| Conservative −20 | 188–75 | 199–70 | **78–34** |
| Half current-season | 187–76 | 198–71 | **78–34** |
| Aggressive +10 | **193–70** | 199–70 | 76–36 |
| Prior profile if no snapshot | 189–74 | **200–69** | **78–34** |

The best-2024 variant (**aggressive +10**) changes Test C's 2024 winners by **+3**, **2025 by zero**, and **2026 by −2**. The conservative variants mostly leave blended picks unchanged and tend to worsen calibration in 2024–2025; 2026 gains are limited to very small Brier changes without additional correct winners.

**This directly reinforces leaving both V1.5 parameters and the fixed market-blend weights alone for now.** An improvement to the independent statistical component need not translate into gains once Test C gets ~83% of its probability from the sportsbook.

## What to investigate next within Test D

**D4: advanced-stat completeness and fallback quality**, rather than changing season weights indiscriminately. Directly quantify false certainty when adjusted EPA is absent but raw EPA is substituted; isolate comparable games by week, opponent-strength and matchup category (P4/P4 vs cross-tier), and test neutral/prior or reliability-weighted EPA shrinkage on strictly pregame information. Preserve frozen 2026 same-odds comparisons, with a true held-out/prospective cohort before deployment.

This test identifies a **plausible structural bug** (treating absent whole-team current-year features as zero instead of preserving the preseason prior), but the historical results do not support deploying the alternate fallback universally; the mechanism is not demonstrated as the cause of high-confidence losses.

## Reproducibility

- `research/test_d_missing_early.py`: pin-free downloadable public schedule/weekly summary data, seven candidate configurations, 2024 selection and independent-year assessment, and missingness cohorts.
- `research/test_d_results.json`: full scores, weekly splits, frozen cohort, source hashes and missing-data subset counts.
- `research/test_d_games.csv`: each matched game, provenance, missingness indicators and predicted probability for every candidate.
- `research/test_d_market_impact.py`: Test D candidates through the original **unchanged** Test C blend, ESPN BET primary opening quotes for 2024–2025 and original frozen quotes for 2026.
- `research/test_d_market_impact.json`: market-eligibility coverage, Brier and winner counts for each candidate.
- `.github/workflows/research-test-d.yml` and `.github/workflows/research-test-d-market-impact.yml`: finished research-only workflows.

**No production code, official Test C blend, value-pick logic, waterfall tiers, or historical official records changed.**
