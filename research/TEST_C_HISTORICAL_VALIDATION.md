# Test C — External Historical Validation of the 70% / 55% Disagreement Alert

**Validation conducted October 13, 2026. Research only: production code and tiers unchanged.**

## Hypothesis frozen before examining historical odds

The 2026 Weeks 5–6 Test C investigation produced the hypothesis:

> **Flag a high-confidence disagreement** when Saturday Forecast V1.5 assigns **70% or higher probability to its chosen winner** and an independently observed, same-game, no-vig sportsbook moneyline assigns **less than 55% to that same chosen team**.

The five archived 2026 discovery-period matchups went **1–4 (20% winners)**. Those five were used to select this threshold and **do not count as independent validation**.

This historical validation applies exactly that rule, without adjusting thresholds or optimizing on 2024–2025 outcomes.

## Data sources and audit

- **Model predictions:** retrospective V1.5 reconstruction from the [Test B game-level dataset](https://github.com/christianmellis1-debug/CFB_Prediction_app/blob/44e7a7cb474e9c19a1af1bfa4774309e6b46b3e6/research/test_b_venue_games.csv), 752 FBS games in 2024 and 762 in 2025. Models were run with current published historic weekly source data. The result is **not a frozen, timestamped historical pregame forecast**; later source revisions and prior model selection involving these seasons are limitations.
- **Archived market:** 1,514 matching ESPN game betting JSON files from [sportsdataverse/cfbfastR-cfb-raw](https://github.com/sportsdataverse/cfbfastR-cfb-raw/tree/main/cfb/betting/json). Use the exact `ESPN BET` provider's `homeTeamOdds.open.moneyLine.american` and `awayTeamOdds.open.moneyLine.american`. Prices on both teams must exist and be plausible from a single book, with two-sided vig of 0–16%. Normalize implied probabilities to remove vig. Opening quotes are historical pregame-market *records*, but the source file was retrieved later and quote timestamps are not independently authenticated.
- **Primary opening-odds coverage:** 717/752 (95.3%) in 2024 and 720/762 (94.5%) in 2025, **1,437/1,514 (94.9%)** combined.
- **Sensitivity:** closing odds for exact ESPN BET provider: 713 2024 +712 2025 =1,425, and an archive's separate ESPN Bet - Live Odds opening quotes on 735+730 =1,465 matchups. Do not use live/current game-state odds for this test.

## Primary results: exact sportsbook opening prices

| Season | Historical odds matches | Warning games | Model correct on warnings | Warning-loss rate |
|---|---:|---:|---:|---:|
| 2024 | 717 | 22 | 9–13 (40.9%) | 59.1% |
| 2025 | 720 | 16 | 6–10 (37.5%) | 62.5% |
| **Combined** | **1,437** | **38** | **15–23 (39.5%)** | **60.5%** |

By comparison, historical model picks of **70% or greater confidence with no warning** went **578–122 (82.6% winner accuracy)** across 700 games. The model's high-confidence warning group underperformed by **43.1 percentage points** on winner accuracy.

The conditional chance of *losing* was **60.5% with the warning**, compared with **17.4% without it in other >=70% model-confidence predictions** (observed loss risk roughly 3.47×). That should not be interpreted causally: it is the risk stratification of existing games with hindsight-reviewed reconstructed model probabilities.

The flagged 38 games represent **2.64% of the primary 1,437-game archived market cohort**. Flagging them would capture 23 of the 427 total model mistakes (~5.4%) while also flagging 15 games the model actually won. It is a precise but fairly rare warning, not an exhaustive filter for bad picks.

**High confidence unflagged by year:**
- 2024: 309–68 (82.0%) in 377 unflagged >=70% confidence predictions, versus warning 9–13.
- 2025: 269–54 (83.3%) in 323 unflagged >=70% confidence predictions, versus warning 6–10.

The apparent gap was large in both years. An exploratory Fisher exact two-sided comparison against unflagged >=70% predictions gives p≈0.000043 in 2024 and p≈0.000095 in 2025. These classical p-values do not account for historical model-selection dependence and possible within-team/week correlations; do not present them as definitive proof of future predictive value.

**Wilson 95% CI** for warning winner accuracy on 38 games is approximately **25.6%–55.3%**, which is wide despite the pooled signal.

## Robustness checks

- **Alternate historical opening provider:** ESPN Bet - Live Odds `open` entries recover 1,465 games; same **38 warned, 15–23**, but only the opening quote is used. Same provider family, so this is a feed-consistency check, not an independent bookmaker test.
- **Historical closing prices:** 1,425 games, warning on **30**, with model **14–16 (46.7%)**. Still considerably worse than similarly high-confidence unflagged games, although weaker and not the identical flagged cohort.
- **Original 2026 discovery period:** 5 warning games, 1–4, should only be cited as discovery, not additive independent validation.

All comparisons use *correct winner*, not against-the-spread or betting profits; high-risk warning **does not imply a profitable opposing wager**.

## Recommendation

The fixed warning has **successfully replicated retrospectively across both 2024 and 2025**, when compared with archived ESPN BET opening prices, but **has not passed a genuinely prospective out-of-sample test**. Because 2024/2025 V1.5 predictions were reconstructed and the 2026 rule was selected after seeing outcomes, it is not justified to describe the warning as established or to change selections directly.

**Recommended next step:** preserve the exact 70% / 55% thresholds without retuning, track on upcoming fresh FBS games using immutable pre-kickoff model picks, provider/time-verified both-sided odds, and final scores. Show a neutral **High-confidence disagreement — review** alert only in shadow/research mode until forward performance is replicated. Do not change V1.5 picks, waterfall tiers, value labels, or bet recommendations automatically.

## Reproducibility

- `research/validate_test_c_historical.py`: download and validate pre-specified warning against 1,514 historical ESPN matchups.
- `research/test_c_historical_validation_results.json`: per-season record, opening/closing sensitivity, coverage, uncertainty and examples.
- `research/test_c_historical_validation_games.csv`: matched historical model and no-vig market probabilities for each archived odds period.
- `research/test_c_historical_odds_coverage.csv`: game-level quote availability and exclusions.
- `.github/workflows/test-c-historical-validation.yml`: research-only GitHub Actions workflow.

All saved on `research/test-c-external-validation-2026-10-13`, not deployed to main.
