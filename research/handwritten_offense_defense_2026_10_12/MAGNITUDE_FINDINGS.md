# Handwritten offense/defense advantage magnitude and point-spread controls

**Completed research: October 12, 2026. No changes to Saturday Forecast production V1.5, official Value tiers or prospectively frozen challenger predictions.**

## Question and precise rule

Using the user's **40% EPA, 25% rushing, 15% passing, 10% turnovers, 10% explosive plays** internal ratings for **both offense and defense**, and the unchanged prior-season/Elo blend, does the magnitude of the ratings predict straight-up wins when the **home team** leads on both?

For a home-team double advantage, define:

`Ogap = proposed_offense_rating(home) - proposed_offense_rating(away)`

`Dgap = proposed_defense_rating(home) - proposed_defense_rating(away)`

A game qualifies if neither is neutral site, Ogap > 0 and Dgap > 0. The primary `min_gap = min(Ogap,Dgap)`, so BOTH must clear a threshold. A +0.5 gap is a standardized rating-unit difference (not 50%). These are retrospective reconstructed, earlier-week ratings, not originally frozen forward picks. The same 2,826 original historical 2022-2026 eligible games are used.

## Non-overlapping magnitude groups, 2022–2026

| Minimum rating advantage (offense and defense) | Correct/qualified | Straight-up win % |
|---|---:|---:|
| 0–0.24 | 202/278 | 72.7% |
| 0.25–0.49 | 185/234 | 79.1% |
| 0.50–0.74 | 108/128 | 84.4% |
| 0.75–0.99 | 90/99 | 90.9% |
| 1.00–1.49 | 94/103 | 91.3% |
| 1.50+ | 33/33 | 100%, tiny extreme-favorite sample |
| **Total** | **712/875** | **81.4%** |

Cumulative (overlapping) minimum gap: >=.25 510/597 (85.4%); >=.50 **325/363 (89.5%)**; >=.75 **217/235 (92.3%)**; >=1.0 **127/136 (93.4%)**. These are NOT ATS win rates and favor much larger sportsbook favorites. The result is likely dominated by team strength/market favorite status.

## Offensive and defensive gaps separately

If 'large' means **>=0.50** standardized units, all 2022–26 qualifying home games split into:

| Offensive advantage | Defensive advantage | Wins/games | Win % |
|---|---|---:|---:|
| Below .5 | Below .5 | 87/130 | 66.9% |
| >=.5 | Below .5 | 160/199 | 80.4% |
| Below .5 | >=.5 | 140/183 | 76.5% |
| **>=.5** | **>=.5** | **325/363** | **89.5%** |

In **2026 Weeks 4–6**, the same groups were 6/9 (66.7%), 5/7 (71.4%), 8/9 (88.9%), and 20/26 (76.9%), respectively. Even the strongest proposed dual-advantage category was not consistently superior over the smaller time window.

## Same weeks' market controls

| Cohort | Rule home favorites | Other home favorites | Strength-adjusted other home favorites |
|---|---:|---:|---:|
| 2023–2025 | 488/582 = 83.8% | 392/587 = 66.8% | **80.7%** |
| 2026 Weeks 4–6 | 39/50 = 78.0% | 36/51 = 70.6% | **85.7%** |

The strength-adjusted control is **stratified by season and signed home-team point-spread bucket**: <7, 7–13.5, 14–20.5, 21+ favorite. Each comparable favorite stratum is weighted by the number of qualifying rule games in it. It removes much (not all) of the heavy-favorite selection bias. Some strata are very small (e.g. only one nonqualifying 21+ point home favorite in 2026 Weeks4–6), so the 2026 -7.7 percentage point gap is **extremely unstable**. The 2023–2025 historical +3.1 percentage point margin is also exploratory and not proof of added value beyond market prices.

Only 50 of 51 Week4–6 rule selections were home favorites; the other home team was +6 and lost. This explains the difference between raw 39/51 (76.5%) and favorite-only 39/50 (78.0%). The underlying 2022 odds source is incomplete, so 2022 appears in **statistical magnitude** analysis but not in substantive **market-matched** comparisons.

2026 W4–6 favorite strength detail:

| Home favorite spread | Rule record | Other favorites |
|---|---:|---:|
| Under 7 | 8/12 | 16/29 |
| 7–13.5 | 9/15 | 15/17 |
| 14–20.5 | 11/12 | 4/4 |
| 21+ | 11/11 | 1/1 |

## Most important qualifications

- Stronger historical ratings usually correspond to larger sportsbook favorites. In 2026 Weeks 4–6, the >=1.0 minimum-gap group went 7–0 but had an **average spread of -32.4**. In 2023–2025 the >=1.0 group went 88/91 with average spread -28.9. Those are overwhelmingly heavy favorites.
- The 2026 W4–6 min>=.5 subset went **20/26 (76.9%)**; the min>=.75 subset went **12/14 (85.7%)**, still including many heavy favorites. Do not mistake a rising historical hit rate for proven excess performance against market expectations.
- Historical odds and retrospective team summaries may have been revised; games were not prospectively archived under this exact formula.
- Line data is ESPN-derived, not a verified DraftKings closing line; we are using spread only to compare **straight-up** winners on similar expected-strength games. No ATS evaluation or profitability claim here.
- Selection was among previously examined seasons; sampling error and exploratory thresholds can overstate reliability. A threshold should be locked *prospectively* before promotion.
- 2022 historical odds are mostly missing and excluded from meaningful market-comparison statistics.
- A high win rate for favorites priced at -1000 or shorter does not prove good bet value.

## Files and reproducibility

- `magnitude_market.py`: same-game earlier-week magnitude score and stratified spread control implementation
- `magnitude_market_results.json`: complete all-seasons/annual/2026 W4-6 and market stratum records
- `magnitude_market_games_2026.csv`: 51 individual 2026 Week4–6 home double-advantage candidates and rating gap sizes
- `tests/test_handwritten_magnitude_market.py`: disjoint-bin, two-unit and market-comparison regression tests
- Workflow: `.github/workflows/handwritten-magnitude-market.yml`

**Research decision:** Do not change live formulas or betting tiers. The next discriminating hypothesis is *whether rating gap improves market-calibrated win probabilities on prospectively frozen games*, not just absolute historical hit rate. Keep underdog / favorite magnitude, and pregame odds/point spreads alongside each future candidate.
