# Saturday Forecast Test G — Weak run offense versus elite run defense

**Research-only test completed October 14, 2026.**

## Exact question

A team that cannot run the ball faces a defense particularly good at stopping the run. Should Saturday Forecast's straight-up prediction explicitly penalize that team in addition to the existing V1.5 football model and sportsbook-informed Test C forecast?

Unlike Test F's general **rushing YPC advantage difference**, this is a one-sided interaction: a **weak rushing offense** (bottom X percentile by earlier FBS rushing yards/carry) specifically playing against a **strong rushing defense** (bottom X percentile by rushing yards/carry allowed, so lower is better). Asymmetric positive matchup signals are assessed independently.

## Feature construction and safeguards

- Use only already-completed **earlier-week FBS-vs-FBS games** and both teams' valid ESPN box scores; calculate pooled rushing yards / pooled attempts for each offense and each team's opponents.
- Rank every eligible team against other teams with prior FBS game histories **as of the target week**, never against final-season stats or current-game box scores.
- Screen percentile thresholds 15%, 25%, 35%, 40%, at least 1/2/3 earlier FBS games, extra YPC gap 0, 1, 1.5, or 2, and direct Test C log-odds penalty coefficients 0–0.75. Compare negative-only, positive-only and combined variants: **1,008 correlated candidate rules**.
- Selection uses 2024 Brier, requiring at least 20 affected and one switched 2024 winner; apply the same rule unchanged to 2025 and 2026.
- Market matchup pool is identical to Test C: 717 games 2024, 720 in 2025, and 221 in 2026 Weeks 3–6. Original V1.5 Weeks 5–6 2026 is frozen, while the other historical V1.5 forecasts are reconstructed. Historical sportsbook open-quote timing is independently unverified.

## Does the matchup signal identify an overlooked losing team?

Using the **prespecified intuitive quartile** (bottom-25%-offense versus best-25%-allowed defense), no extra minimum YPC gap and one prior FBS game, count matchups where *only one side* qualifies. Then compare **the disadvantaged team's actual wins** to the *sum* of its Test C prior win probabilities:

| Period | Qualifying games | Disadvantaged team wins | Test C expected disadvantaged wins | Actual rate | Expected rate |
|---|---:|---:|---:|---:|---:|
| 2024 | 34 | **10** | 8.59 | 29.4% | 25.3% |
| 2025 | 32 | **10** | 7.55 | 31.3% | 23.6% |
| 2026 Weeks 3–6 | 12 | **6** | 4.42 | 50.0% | 36.8% |
| 2026 original frozen W5–6 subcohort | 5 | **2** | 1.50 | 40.0% | 30.0% |

**This is counter to the proposed automatic penalty**: teams with the matchup disadvantage won slightly *more* than the original Test C estimate. Samples are small and heavily confounded by other strengths, opponent power, home field and market price, so no conclusion about the causal effect of rushing weakness can be drawn.

## Backtest direct Test C probability adjustments

The 2024-selected rules are:

| Rule family | Selected rule | 2024 Test C wins / 717 | 2025 / 720 | 2026 W3–6 / 221 | 2026 frozen W5–6 / 112 |
|---|---|---:|---:|---:|---:|
| **Unchanged Test C** | 16.93% V1.5 / 83.07% market | **509** | **527** | **169** | **78** |
| Weak offense vs strong defense **penalty only** | Bottom 35% for both metrics, >=1 prior game, beta +0.10 | 508 | 526 | 168 | 78 |
| Strong offense vs weak defense **bonus only** | Top/bottom 40%, YPC difference >=1, beta +0.75 | 510 | 525 | 169 | 78 |
| Both penalty + bonus | Bottom/top 35%, gap >=1, beta +0.75 | 510 | 527 | 168 | 78 |

The 2024-selected **penalty-only rule produces one additional mistake in each of 2024, 2025 and 2026 Weeks 3–6**. Its Brier improves very slightly in 2024 (**+0.000011**) and 2025 (**+0.000074**), but **worsens markedly in 2026 (−0.000779)** and frozen 2026 Weeks 5–6 (−0.000806). The most aggressive positive + negative combined rule wins one extra 2024 game but loses one more in 2026 and has worse Brier in both later-year cohorts.

No demonstrated, replicating benefit justifies an automatic probability penalty. **Do not deploy these candidate coefficients.** The mismatch is meaningful football context, but not an independent win-probability edge in the examined sample.

## Product response

The user also reasonably wants **the matchup to be visible and captured** when viewing predictions. A separate production-candidate UI feature on `feature/rushing-matchup-diagnostic-2026-10-14` is designed to report both prior FBS rushing YPC and yards/carry allowed, identify exactly this weak-offense-versus-strong-defense percentile pairing, and keep it behind a compact card-details expander. Crucially, it **does not fabricate a win-probability adjustment**, change Test C weights, or overwrite six tier selections.

This allows ongoing prospective evidence collection and clear football-specific explanations, without introducing a backtest-supported negative adjustment that historically worsened the correct-winner record.

## Limitations / next validation

2024/25 forecasts use reconstructed V1.5, not authentically frozen originals. Historical opening quotes lack independent capture-time verification. The source box archives may have been revised after past matchups. 1,008 configurations tested create heavy multiple-comparison risk, and the disadvantaged matchup contains just **78** games across the main three periods. A stronger causal claim requires out-of-season validation, opponent-quality stratification and more realistic expected rushing efficiency models. Future research should compare conditional point/spread errors and actual team rush production when such outcomes are cleanly available, rather than assume winner penalty.

## Reproducibility

- `research/test_g_asymmetric_run.py` — computes historical percentile profiles, direct probability overlays, outcome-calibration counts and Brier.
- `research/test_g_asymmetric_run_results.json` — full candidate grid and selected metrics.
- `research/test_g_asymmetric_run_games.csv` — each game's prior-only raw run profile and mismatch flags.
- `.github/workflows/test-g-asymmetric-run.yml` — successful reproducible research workflow.

**Production main branch and independent betting tiers were not changed by the research.**
