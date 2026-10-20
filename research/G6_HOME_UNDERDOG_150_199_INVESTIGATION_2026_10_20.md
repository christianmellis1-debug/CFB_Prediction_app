# Priority 2: G6 Home Underdogs, +150 through +199
**Research audit 2026-10-20 · informational flag only**

## Fixed candidate and history

The *new* prospective research screen identifies G6-vs-G6 FBS games in which independent (pre-market) V1.5 picks the **home** team to win, the chosen home side is an underdog on same-sportsbook paired moneylines, and its American moneyline is **+150 through +199 inclusive**. A parallel **secondary** research bucket tracks +200 or longer; neither research bucket is a new official betting tier, changes the predicted winner, changes existing official waterfall selections, or authorizes a recommended wager. Existing G6 Confidence Conflict exclusions retain priority.

Historical sources:
- 2024–2025: season-by-season reconstructed independent V1.5 and ESPN BET opening prices; prices are archive labels without externally authenticated capture times.
- 2026 Weeks 3–4: retrospectively reconstructed V1.5 and DK historical opening lines.
- 2026 Weeks 5–7: genuine immutable pregame V1.5 snapshots and recorded DK prices.
- 2026 Weeks 1–2 excluded due to thin model data, per research instruction. Earlier years retain Week 2, but note two 2025 Week-2 wins and no same-year FBS pregame stats for one of them.
- 2026 Pac-12 treated as G6. Historical Pac-12 2024/25 excluded from G6.

## Matched price-window test

All qualifying G6 **home sportsbook underdogs +150 to +199** with a matched model estimate and market quote (n=56):

| Independent V1.5 action | N | Record | Average market no-vig p | $100/bet net | ROI |
|:--|--:|--:|--:|--:|--:|
| Picks home underdog | 12 | **9–3** | 35.8% | **+$1,210** | **+100.8%** |
| Picks opposing favorite | 44 | **14–30** | 35.4% | −$575 | −13.1% |
| Everyone | 56 | 23–33 | 35.5% | +$635 | +11.3% |

The groups have similar **priced sportsbook chances**, but not the same team quality. V1.5 picks have average pregame home-vs-away Elo gap −12; rejected dogs average **−198**. Some of the outcome difference may arise because the statistical model recognizes relatively competitive teams in the same narrow price range.

By season for selected candidates: **2024 2–0 (+167.5% ROI)**; **2025 6–2 (+100.6%)**; **2026 Weeks 3–7 1–1 (+35%)**. The candidate after excluding Week 1–2 for ALL years: **7–3 (+87.0%)**. Retrospective success must not be called an out-of-sample test.

A null test treating archived no-vig market prices as unbiased independent win probabilities expects approximately 4.30 wins from the 12; probability of nine or more is **0.00666** (Poisson-binomial calculation). Probability for returns at least the observed +100.8% by Monte Carlo market-probability simulation was roughly **0.0053**. A one-sided Fisher contingency contrast of 9/12 vs 14/44 is about **0.009**. **These are unadjusted exploratory p-values**: the +199 threshold, home-vs-road subgroup, and other choices were selected after examining historical outcomes, so these numbers do NOT establish prospective statistical significance.

## Investigated football covariates

Previous football statistics use only eligible earlier-season completed FBS/FBS games that kicked off *before* the target game. No target or future results are included.

| Prior/diagnostic metric | V1.5-selected home +150–199 | Other home +150–199 |
|:--|--:|--:|
| Previous offensive points per eligible FBS game | 21.1 | 19.8 |
| Previous points allowed per eligible FBS game | 29.5 | 32.4 |
| ESPN pregame Elo home minus away | **−12** | **−198** |
| Model home-win estimate | 59.9% | 32.5% |
| Average sportsbook no-vig home win probability | 35.8% | 35.4% |
| Average moneyline | +169 | +173 |

Within V1.5-selected 12, winner-versus-loser scoring differences do NOT justify tightening selection:

- Home pregame points/game **>=20**: 5–2, +90.7% ROI. This eliminates two wins and one loss and underperforms original +100.8%.
- Home pregame points allowed **<=30**: 3–1, +108.7%, but drops five winners and two losers; unsupported at four games.
- **Both** scoring >=20 and allowed <=30: 2–1, +81.7%; loses more coverage and ROI.
- Pre-existing home Elo advantage: too few games to conclude a reliable result; simply controlling home-away Elo within 100 yields **9–7 (+53.8% ROI)** across all market-matched +150–199 home underdogs, versus **9–3 (+100.8%)** in V1.5-selected.
- Independent model >=60% within +150–199: 4–0 (+165% ROI), but only four bets; another post-hoc cut would increase overfit risk.
- The market-implied probability was **not** dramatically different among winners and losers within the narrow price bucket; selection based solely on sportsbook price remains weak.

Thus prior PPG and points allowed appeared to separate winners when using **all +150+ home dogs**, but **within the +150–199 research bucket they no longer separate consistently**. Elo gap may account for some selection quality, and the broader independent model may be doing something beyond Elo; larger forward samples and opponent-adjusted stats are needed.

## Confidence, sampling and implementation

- Flat-stake ROI in the candidate is +100.8% across 12 matches; a Wilson 95% interval for its **win proportion** is about 46.8% to 91.1%, reflecting sample uncertainty.
- Sample and threshold have been repeatedly mined; these results cannot establish a long-run expected ROI or justify promoting a wagering tier.
- The 2026 original prospective portion contains just **one** winner, UAB vs East Carolina (+170), alongside one Week-4 retrospective loss (Sacramento State vs Massachusetts, +185). Strong historical results might be model/backtest overfit.
- Week 8 original immutable snapshot does not include a selected +150–199 **G6 home** underdog as of the captured archive. Subsequent valid pregame price changes might create candidates.
- The app **does not filter** additional price characteristics by pregame scoring or Elo because they have not survived an independent holdout. Instead the +150–199 primary research flag and +200+ secondary tracking label are prospective, and the original G6 high-risk no-bet logic remains unchanged.

## Next rigorous test

1. Freeze +150–199 primary flag now and keep the +200+ secondary cohort unmodified, collecting price source, captured timestamp, model, venue, and outcomes.
2. Track the 2026 remaining schedule and next season without retuning thresholds.
3. Compare matched non-picks by price, season, team quality and pregame schedule strength, including opponent-adjusted offensive/defensive efficiency, rushing YPC allowed, turnovers and injuries *only if valid pre-kickoff sources can be recovered*.
4. Validate profitability versus offered sportsbook closing line after accounting for vig/slippage, and prioritize downside/stability rather than historical ROI alone.
5. Do not automatically elevate from research to Value Pick or parlay without independent validation.

## Sources
- [2024–2025 model and ESPN BET quote archive](https://github.com/christianmellis1-debug/CFB_Prediction_app/blob/research/test-c-historical-blend-2024-2025-2026-10-13/research/test_c_blend_2024_2025_games.csv)
- [2026 Weeks 3–4 reconstructed model and DK opening quote archive](https://github.com/christianmellis1-debug/CFB_Prediction_app/blob/research/test-c-head-to-head-weeks3-6-2026-10-13/research/test_c_head_to_head_weeks3_6_games.csv)
- [2026 frozen original model forecasts](https://github.com/christianmellis1-debug/CFB_Prediction_app/blob/main/data/shadow_tracking.json)
- [Full 19-game G6 home-underdog audit](https://github.com/christianmellis1-debug/CFB_Prediction_app/blob/main/research/G6_HOME_UNDERDOG_RESEARCH_2026_10_20.md)
