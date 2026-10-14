# Saturday Forecast — Test H: Weak run + pass offense vs strong rushing defense

**Completed 2026-10-14. Research-only; no changes to Test C, V1.5, passing-YPA experimental model, or six independent value tiers.**

## Hypothesis

User's football-specific hypothesis: **When a team is weak both rushing and passing, and the opponent is strong at stopping the run, the resulting offensive constraint should increase the likelihood of losing beyond current overall offense/defense ratings and sportsbook information.** Evaluate whether a further penalty to that side's win probability actually improves calibrated prediction accuracy.

### Data and leakage controls

- Historic market-quoted cohorts: **717 FBS games in 2024**, **720 in 2025**, and **221 in 2026 Weeks 3–6** (112 in originally frozen V1.5 Week 5–6 subset).
- Two-sided sportsbook moneyline no-vig Test C fixed at **16.927926947% V1.5 / 83.072073053% market**.
- All rush and pass features aggregated exclusively from matched valid box scores of **earlier completed FBS-vs-FBS games**, strictly prior to the matchup week. Offensive rushing yards per carry, net pass yards per attempt, completion %, defensive rushing YPC allowed, and net passing YPA/completion allowed are pooled across all prior FBS snaps.
- Percentiles for weak/strong teams are calculated **week-by-week against teams with eligible prior FBS game histories**; no end-of-season rankings. Bottom 25% rushing YPC + bottom 25% passing YPA = doubly weak offense; opposing rush defense in **bottom 25% of YPC allowed** = top-25% run-stopping ability. In stricter variant, its pass defense must also be bottom-25% YPA allowed.
- For all qualifying tests, feature availability and previous FBS game count are explicitly tracked; missing pregame boxes do not trigger rules.
- 2024/2025 V1.5 historical predictions are retrospective; Week 3–4 of 2026 retrospective; Week 5–6 of 2026 original V1.5 archived, but feature reconstruction and sportsbook opening quotes still rely on historical source vintages without individually verified timestamp captures.

## Fixed intuitive diagnostic: 25th-percentile threshold (not optimized)

A matchup flags the **disadvantaged side**, not necessarily the game winner. The check is whether those sides actually lose more than Test C expects them to lose. Expected wins are `sum(P_TestC for the disadvantaged sides)`; these can be compared to their observed wins.

| Rule | 2024: games; actual vs expected disadvantaged wins | 2025 | 2026 Weeks 3–6 | Frozen 2026 W5–6 |
|---|---|---|---|---|
| Weak rush offense vs strong run defense | **54; 14 vs 14.00** | **73; 21 vs 18.20** | **22; 9 vs 7.55** | **9; 4 vs 3.01** |
| **Both weak run and weak passing YPA vs strong run defense** | **23; 5 vs 4.25** | **16; 6 vs 3.03** | **7; 3 vs 2.24** | **2; 1 vs 0.48** |
| Both weak run/pass vs **strong run and strong pass defense** | **12; 3 vs 1.76** | **6; 1 vs 0.59** | **2; 1 vs 0.29** | **0; none** |

**Important distinction:** these teams have relatively low baseline chances to win (e.g. 4.25 expected / 23 games = **18.5%** in 2024). But the sample does **not** establish that Test C has systematically *overrated* them. The doubly weak offense won **14 of 46** flagged games across all three cohorts, versus **9.52 expected**, so an additional win-probability *penalty* points opposite to the observed residuals. This is not evidence that poor rushing or passing are helpful—both are correlated with many other strengths, opponent quality, home field and odds. It is evidence against arbitrarily subtracting probability on top of the existing market model.

### Fully specified candidate grid

Four rule families: (1) bottom-ranked rushing YPC offense + bottom-ranked passing YPA offense versus elite run defense; (2) same but elite run **and** pass defense; (3) bad rushing YPC + bad completion % offense vs elite run defense; (4) same completion definition plus elite pass defense.

Each family screened percentile thresholds **20/25/33/40%**, minimum prior FBS games **1/2/3**, and penalty log-odds coefficient **−0.30/−0.15/0/+0.10/+0.20/+0.35/+0.50/+0.75** = **384 candidate rules**. Selecting rules by minimum 2024 Brier, requiring at least five one-sided qualifying 2024 games and a positive penalty, then evaluating unchanged on 2025 and 2026.

For a disadvantaged home team, subtract `beta` from the current Test C home-win log odds; for a disadvantaged away team add it. If both teams qualify the adjustments cancel.

### 2024-selected rule results vs Test C

| Candidate description | 2024 / 717 | 2025 / 720 | 2026 W3–6 / 221 | Frozen 2026 W5–6 /112 |
|---|---:|---:|---:|---:|
| **Current Test C** | **509–208** | **527–193** | **169–52** | **78–34** |
| Weak run + weak passing YPA vs top-33% run defense; beta .50 | **510–207** | 527–193 | **168–53** | 78–34 |
| Weak run + weak passing YPA vs strong run **and** pass defense; top/bottom 40%, beta .10 | 509–208 | 527–193 | 168–53 | 78–34 |
| Weak run + weak completion % vs strong run defense; top/bottom 33%, beta .20 | 509–208 | **529–191** | 168–53 | 78–34 |
| Weak run + weak completion % vs strong run **and** pass defense; top/bottom 33%, beta .10 | 509–208 | 527–193 | 169–52 | 78–34 |

No 2024-selected rule raises straight-up accuracy **consistently** in 2025 and 2026.

Brier examples: strongest 2024 rushing+YPA signal goes **0.1834894 → 0.1832269** in 2024, but **0.1822763 → 0.1828473** in 2025 (worse) and **0.1701468 → 0.1716323** in 2026 (worse). Frozen W5–6 2026 likewise deteriorates **0.1978725 → 0.1998428**. The 2026 passing-efficiency plus rushing-offense penalty flips **three winner selections**: fixes Baylor at Arizona State, but breaks Troy at Utah State and Syracuse at UConn, net one extra error.

### Directly compare with Test F's leading passing-YPA challenger

Test F had shown a small historical improvement from **adding +0.10 × normalized prior-FBS passing YPA matchup differential to Test C's log odds**.

We independently tested whether a specifically proposed **additional** double-weakness penalty at the intuitive unoptimized quartile threshold adds beyond Test F, beta **+0.20**, min 1 prior FBS game. This is the sharper value-added check.

| Cohort | Test F passing-YPA challenger | Test F + double-weak rushing/pass penalty | Incremental result |
|---|---:|---:|---|
| 2024 | **511–206**; Brier **0.1833969** | 511–206; Brier 0.1834071 | No winner gains, Brier worse |
| 2025 | **529–191**; Brier **0.1822193** | 528–192; Brier 0.1825445 | One fewer winner, Brier worse |
| 2026 W3–6 | 170–51; Brier **0.1699793** | 170–51; Brier 0.1702600 | No winner gains, Brier worse |
| 2026 frozen W5–6 | 78–34; Brier **0.1974862** | 78–34; Brier 0.1979963 | No winner gains, Brier worse |

Thus the double-weakness rule **does not add demonstrated information** after existing passing-YPA information. It sometimes duplicates known weaknesses or introduces poorly calibrated conviction.

### Decision and limitations

**Do not change Test C probabilities or V1.5 weights to force a penalty based on this intersection.** It is a useful descriptive mismatch, not a validated separate win-probability coefficient. Do not use it as an official new waterfall betting tier or sell it as a betting advantage.

Historical selection and multiple testing can inflate positive 2024 effects; 384 correlated candidates were considered. Only **46** intuitively qualifying run+pass weak/run-defense strong games occurred across the three main cohorts (23/16/7). Stricter strong-run-and-pass defense pairing had **20 games** across all three cohorts (12/6/2), too few to make a confident rule. Future registered tests should expand the sample, control for opponent quality and baseline bookmaker implied chances, and separate risk **flagging** from winner prediction.

The production Game Cards already contain a collapsible prior-FBS **Rushing Matchup** section from PR #22. It can be extended to display *passing weakness alongside rushing weakness* without pretending it adds a validated predictive edge. Such an informational UI extension would not change Test C or the tiers.

## Reproduce

- `research/test_f_rush_pass_matchups.py` copied unchanged from Test F's verified FBS-only team-box parser.
- `research/test_h_double_weakness.py` — percentile features, 384-rule grid, 2024 selection, 2025–26 checks, fixed quartile expected-versus-actual diagnostics and incremental Test F comparison.
- `research/test_h_double_weak_results.json` — full per-rule season and frozen cohort metrics, source audits.
- `research/test_h_double_weak_games.csv` — original Test C prices, prior FBS rushing/pass rates, four selected condition flags, adjusted predictions.
- `.github/workflows/test-h-double-weakness.yml` — completed successful 2026-10-14 GitHub Actions run.

**No changes to production model, live Test C, betting tiers or official historical results.**
