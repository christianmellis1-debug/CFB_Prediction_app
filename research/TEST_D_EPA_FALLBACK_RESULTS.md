# Saturday Forecast — Test D2: Missing Adjusted EPA / Raw EPA Fallback

**October 13, 2026 — Completed historical investigation; no change to production Test C, V1.5, or six-tier waterfall.**

## Research hypothesis and exact methods

V1.5 treats `adj_off_epa` and `adj_def_epa` as 40% of their respective offensive and defensive composite ratings. If adjusted EPA is absent in a weekly team summary, V1.5 substitutes raw EPA (`EPAplay_off` / `EPAplay_def`) and then **standardizes the resulting mixed adjusted/raw vector as one cross-sectional z-score**. Adjusted EPA is a cumulative opponent-adjusted regression estimate from games through the week; raw EPA is an unadjusted per-play measure. Both use strictly preceding-week snapshots for each matchup.

Six challengers, with all non-EPA features unchanged:
1. **Raw-only EPA:** use raw per-play EPA everywhere, even when adjusted EPA exists.
2. **Missing neutral:** preserve adjusted EPA where available; set a missing adjusted EPA component's normalized z-score to zero (ignore its raw replacement).
3. **Shrink raw fallback to 25%, 50%, or 75%:** compute the current mixed-source z-score, but scale down the score *only* for teams lacking adjusted EPA.
4. **Separately standardize raw and adjusted:** for each week derive separate league z-scores for raw and adjusted EPA, using standardized raw only where adjusted missing.
5. **Control:** untouched V1.5 adjusted-first, raw-when-missing pipeline.

Selection criterion fixed **before outcome inspection**: minimum Brier on 2024 Weeks 1–6, then measure unchanged 2025 Weeks 1–6, full 2024/2025, and archived Week 5–6 2026.

## Key diagnostic — EPA completeness changes sharply by week

| Team summary snapshot | Adjusted offense EPA coverage | Adjusted defense EPA coverage | Raw offense / defense coverage |
|---|---:|---:|---:|
| 2024 through Week 1 | **3/75** | 3/75 | 75/75 |
| 2024 through Week 2 | **40/130** | 40/130 | 130/130 |
| 2024 through Week 3 | 114/133 | 114/133 | 133/133 |
| 2024 through Week 4 | 131/133 | 131/133 | 133/133 |
| 2024 through Week 6 | **134/134** | 134/134 | 134/134 |
| 2025 through Week 1 | **3/93** | 3/93 | 93/93 |
| 2025 through Week 2 | **58/135** | 58/135 | 135/135 |
| 2025 through Week 3 | 121/136 | 121/136 | 136/136 |
| 2025 through Week 4 | **136/136** | 136/136 | 136/136 |
| 2026 through Week 1 | **8/94** | 8/94 | 94/94 |
| 2026 through Week 2 | **58/137** | 58/137 | 137/137 |
| 2026 through Week 3 | 133/138 | 133/138 | 138/138 |
| 2026 through Week 4 | **138/138** | 138/138 | 138/138 |
| 2026 through Week 5 | **138/138** | 138/138 | 138/138 |

Thus by pregame **2026 Week 5**, every team had adjusted EPA in its previous-week summary. **All 112 frozen 2026 Weeks 5–6 matchups used adjusted EPA, not raw fallback.** This is direct evidence that raw-EPA fallback did not cause the Week 6 accuracy decline.

Where both were present, adjusted and raw per-play EPA were strongly correlated (2024 Week 2 offense r≈0.936, defense r≈0.950; later weeks often r≈0.86–0.94). Correlation does not establish interchangeability against different opponents.

## V1.5 head-to-head on identical FBS games

| Method | 2024 W1–6 / 295 | 2025 W1–6 / 296 | Frozen 2026 W5–6 / 112 |
|---|---:|---:|---:|
| **Current V1.5** | **211–84** | 209–87 | **77–35** |
| Raw-only EPA | **213–82** | **212–84** | 75–37 |
| Neutral missing adjusted EPA | 210–85 | 210–86 | **77–35** |
| Shrink fallback 25% | 209–86 | 210–86 | **77–35** |
| Shrink fallback 50% | 211–84 | 209–87 | **77–35** |
| Separate raw and adjusted z-scoring | 211–84 | 209–87 | **77–35** |

Raw-only wins **2024 selection** on Brier (0.179285 vs baseline 0.179832), but slightly worsens the 2024 log loss (0.527891 vs 0.526691). In **2025 Weeks 1–6**, raw-only improves winners by 3 but worsens Brier (**0.185472 vs 0.184023**) and log loss. In **2026 archived Weeks 5–6**, raw-only loses two more games and significantly worsens Brier (**0.215775 vs 0.208983**). Because adjusted EPA was available on those weeks, switching to raw-only introduces a different problem rather than addressing missingness.

**Full 2024 season (752 FBS games):** baseline 536–216, raw-only 540–212, with Brier worsened **0.187913→0.189567**. **Full 2025 season (762 games):** baseline 546–216, raw-only 546–216, with Brier worsened **0.183029→0.184500**.

Other missing-only methods make almost no difference after Week 4 because adjusted EPA has become broadly complete. Separate standardization in 2025 reduces Brier marginally (**0.183029→0.182840** full season) but changes **zero winner selections**; in 2024 it changes zero winners and improves Brier by only 0.000019.

## Missingness-specific and matchup-type findings

In Weeks 1–6, 2024 had **100/295 games** with at least one actual raw EPA fallback (the baseline went 76–24); 2025 had **98/296 games** (baseline 66–32). Other games flagged as having missing adjusted EPA may instead lack an entire previous-week team snapshot, which is a separate fallback problem handled in Test D Part 1.

When actual raw EPA fallback was used:
- 2024: baseline **76–24**, raw-only alternative **74–26**, half-strength fallback **76–24** with slightly lower Brier.
- 2025: baseline **66–32**, raw-only alternative **67–31**, half-strength fallback **66–32**, with separate z-scoring giving a small probability-quality gain.
No consistent directional raw-fallback winner penalty appears across years.

**Opponent/matchup categories**, Weeks 1–6:

| Group | 2024 V1.5 → raw-only | 2025 V1.5 → raw-only | Frozen 2026 V1.5 → raw-only |
|---|---:|---:|---:|
| P4 vs P4 | 70→70 / 110 | 62→63 / 101 | 31→30 / 50 |
| P4 vs non-P4 | 80→81 / 88 | 81→81 / 94 | 4→5 / 6 |
| non-P4 vs non-P4 | 61→62 / 97 | 66→68 / 101 | 42→40 / 56 |

This is a simple descriptive partition, not a controlled estimate of causal opponent bias. Raw-only changes were sparse across each category and did not show a robust edge on tougher P4-vs-P4 matchups. The source's weekly rating calculation accounts for opponents in adjusted EPA; raw per-play EPA is not a substitute for that by design.

## Test C: does EPA substitution change the live 16.93% / 83.07% predictor?

The **Test C blend weights were fixed**; only V1.5's source EPA formulation changed. 2024/25 are paired against archived **ESPN BET opening odds**. 2026 are paired against originally frozen same-book pregame market probabilities.

| Fixed Test C with ... | 2024 W1–6 / 263 | 2025 W1–6 / 269 | Frozen 2026 W5–6 / 112 |
|---|---:|---:|---:|
| Original V1.5 EPA input | **190–73** | **199–70** | **78–34** |
| Raw-only V1.5 EPA | 191–72 | **199–70** | 77–35 |
| Half-strength fallback | 190–73 | **199–70** | **78–34** |
| Separate raw/adj standardization | 190–73 | **199–70** | **78–34** |

**Across full 2024/25 quoted games:** raw-only changes final Test C picks by **+3 in 2024** (509→512 of 717) and **+3 in 2025** (527→530 of 720), but Brier worsens in 2024 (0.183489→0.183616), improves marginally in 2025 (0.182276→0.182214), and **worsens in frozen 2026** (0.191192→0.192032, with one more winner mistake).

As in prior Test D research, 2024/2025 model probabilities are retrospective V1.5 reconstructions, and alternative 2026 model predictions are **retrospective log-odds deltas on true frozen V1.5** rather than contemporaneously locked challengers. 2026 odds are originally captured while historical odds are from an archival feed with independently unverified quote timing.

## Decision

**Do not deploy an adjusted-to-raw EPA fallback change or replace adjusted EPA with raw universally** on this evidence.

- The fallback is **common very early** (especially after Week 1) but naturally disappears when adjusted EPA ratings are available.
- It is **not the culprit for the specific 2026 Weeks 5–6 decline**.
- Raw-only improves some retrospective winner counts but consistently worsens probability accuracy across key seasons, and introduces new errors in the frozen 2026 cohort.
- Neither reducing nor separate standardization of raw fallback yields a reproducible meaningful lift in primary Test C predictions.

**Better next Test D candidate:** instead of EPA missingness, evaluate **confidence/reliability of available adjusted EPA based on number and strength of prior FBS opponents** (e.g. teams rated after just 2–3 games), with weekly preregistered thresholds and testing across tough same-tier games. This is a different mechanism from missing adjusted EPA.

## Reproduction and production-safety audit

- `research/test_d_epa_fallback.py`: loads cumulative 2024–26 weekly summaries and event schedules; faithfully reconstructs all original V1.5 EPA inputs, runs six EPA alternatives and retains strict pregame-week snapshots.
- `research/test_d_epa_fallback_results.json`: model and blended outcomes, completeness by week, source hashes and cohort categories.
- `research/test_d_epa_fallback_games.csv`: full per-game predictions, actual winners, missingness flags and market probabilities.
- `.github/workflows/research-test-d-epa-fallback.yml`: successful reproducible isolated research workflow.
- Public field meaning: [sportsdataverse CFB loaders](https://js.sportsdataverse.org/docs/cfb/reference/loaders).

**No production app code, V1.5 parameters, fixed Test C blend, or tier selections changed.**
