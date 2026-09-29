# Team tendencies: preliminary box-score experiment

Scope: 2024 and 2025 regular seasons; 2026 through Week 4. 1,302 games, 2,604 team observations. P4 vs P4 and G6 vs G6 only; Notre Dame P4. Earlier-week current-season FBS history only. No production or frozen Week 5 picks changed.

## Method

Rush share = prior rushing attempts / (prior rushing attempts + prior pass attempts), aggregated over prior games. Run majority means >50%; pass majority <50%; exactly 50% is separate. Rush/pass advantages use the existing matchup estimates. Threshold and weighting formula fixed before inspecting this test.

Weighted candidate: replace the rushing advantage vote with 2 × own rush share, and the passing advantage vote with 2 × own pass share. Defense, turnover and home venue remain one point each. Higher score wins; exact equal scores abstain. These are arbitrary exploratory weights, not fitted probabilities.

## Pooled records by offensive advantage and tendency

| Group | Advantage | Tendency | Record | Win rate |
|---|---|---|---:|---:|
| G6 | Both | Balanced | 5–1 | 83.3% |
| G6 | Both | Pass majority | 45–28 | 61.6% |
| G6 | Both | Run majority | 191–90 | 68.0% |
| G6 | Neither | Balanced | 1–1 | 50.0% |
| G6 | Neither | Pass majority | 44–97 | 31.2% |
| G6 | Neither | Run majority | 74–143 | 34.1% |
| G6 | Pass only | Balanced | 1–2 | 33.3% |
| G6 | Pass only | Pass majority | 51–75 | 40.5% |
| G6 | Pass only | Run majority | 64–82 | 43.8% |
| G6 | Rush only | Balanced | 1–0 | 100.0% |
| G6 | Rush only | Pass majority | 24–29 | 45.3% |
| G6 | Rush only | Run majority | 134–87 | 60.6% |
| P4 | Both | Pass majority | 58–34 | 63.0% |
| P4 | Both | Run majority | 239–79 | 75.2% |
| P4 | Neither | Balanced | 2–2 | 50.0% |
| P4 | Neither | Pass majority | 48–94 | 33.8% |
| P4 | Neither | Run majority | 63–201 | 23.9% |
| P4 | Pass only | Balanced | 3–1 | 75.0% |
| P4 | Pass only | Pass majority | 51–49 | 51.0% |
| P4 | Pass only | Run majority | 69–84 | 45.1% |
| P4 | Rush only | Balanced | 0–2 | 0.0% |
| P4 | Rush only | Pass majority | 29–28 | 50.9% |
| P4 | Rush only | Run majority | 105–93 | 53.0% |

## Same-game model test

| Season | Group | Paired games | Six-metric wins | Weighted wins |
|---|---|---:|---:|
| 2024 | G6 | 241 | 165 | 165 |
| 2024 | P4 | 258 | 177 | 177 |
| 2025 | G6 | 248 | 149 | 149 |
| 2025 | P4 | 242 | 172 | 172 |
| 2026 | G6 | 40 | 27 | 27 |
| 2026 | P4 | 39 | 24 | 25 |

Same 1,068 games: baseline 714–354 (66.9%), weighted 715–353 (66.9%). Only changed pick: 2026 Virginia → West Virginia, a correct change. This is not meaningful evidence of improvement.

Weighting additionally selected 181 games where baseline abstained: 101–80 (55.8%). G6: 55–29; P4: 46–51. These are different coverage, not a head-to-head improvement. All weighted selections: 816–433 (65.3%), versus baseline 714–354 (66.9%) on its smaller set.

## Interpretation

G6 rush-only advantage: run-majority 134–87 (60.6%) vs pass-majority 24–29 (45.3%). Direction consistent across the three seasons, but 2026 pass-majority sample is only four games. P4 rush-only effect was small pooled and changed direction across seasons. P4 pass-only advantage: pass-majority 51–49 vs run-majority 69–84; G6 pass-only: pass-majority 51–75 vs run-majority 64–82. No universal tendency bonus is supported.

## Limits and next step

This is a box-score usage proxy, not neutral-situation play calling. It does not remove kneel-downs, scrambles, sacks, or score-state effects. Winning in prior games can itself cause higher run share. Opponent quality, game state and strength are not controlled; the associations are not causal. Completion rate is not full passing efficiency. Team observations include both sides of each game and are dependent. Historical input feeds may be revised; these are reconstructed pregame features, not original archived picks. No odds/profit test. Prior research used these seasons, so they are not untouched holdouts.

Recommendation: retain tendencies as a research variable. Before adding weights, repeat using play-by-play designed runs and dropbacks in close-score/early-game situations, then test on held-out games. Do not change production based on this pilot.

by_season.csv contains all subgroup records. team_details.csv contains computed features; game_comparison.csv contains candidate picks and results. run.py expects the prior turnover_test source directory alongside this directory.
