# Handwritten offense/defense ratings + home field — 2026-10-12

**Status: Completed historical research. No live V1.5 prediction, Value Shortlist rule, or prospective archive changed.** The exact user's unit weights are offense/defense 40% EPA, 25% rushing YPC, 15% completion rate, 10% turnovers, 10% explosive plays; no success or red-zone. The original production model already includes **20% historical home/road performance** outside those units. We therefore evaluated two separate home questions:

1. When both handwritten ratings favor a team, does that team win more often at home than away, excluding neutral sites?
2. Changing ONLY the historical home/road coefficient to 0%, 10%, 20% (existing), 30% or 40%—or adding a small fixed home log-odds bonus on top—improves or worsens the handwritten prediction on the exact same 2,826 games?

All 2022–2025 full regular-season observations and 2026 completed Weeks 3–6 use **earlier-week** available complete two-sided FBS box scores and season summaries. Team statistical differences are blended with unchanged prior-season Elo/efficiency as in the previous handwritten A/B tests. Non-neutral home field is derived using the **actual production** prior-week home/away history function. Neutral-site games receive no home adjustment and are analyzed separately.

## Condition win rates

| Condition | Record | Correct |
|---|---:|---:|
| Home team overall, nonneutral | 1597-1153 | 58.1% |
| **Home team better on BOTH handwritten offense and defense** | **712-163** | **81.4%** |
| **Away team better on BOTH handwritten offense and defense** | **525-242** | **68.4%** |
| Better at both at a neutral site | 28-10 | 73.7% |
| Home better on offense (any defense) non-neutral | 1044-373 | 73.7% |
| Home better on defense (any offense) non-neutral | 1023-418 | 71.0% |
| Offense and defense split different teams, home team win | 643-465 | 58.0% |

**Season breakdown of both-advantage win rate:**

| Season | Home two-advantage record | Away two-advantage record |
|---|---:|---:|
| 2022 | 146/191 (76.4%) | 98/160 (61.3%) |
| 2023 | 165/198 (83.3%) | 139/182 (76.4%) |
| 2024 | 184/219 (84.0%) | 110/174 (63.2%) |
| 2025 | 150/185 (81.1%) | 127/181 (70.2%) |
| 2026 W3–6 | 67/82 (81.7%) | 51/70 (72.9%) |

The differences above are **not** causal effects of venue: home and away both-advantage pools are distinct and may differ on team quality, market price, competition or injuries.

## Paired predictive effects (2,826 exact same games)

| Formula/scenario | Correct / games | Accuracy | Brier (lower better) |
|---|---:|---:|---:|
| **Production V1.5** | **2013 / 2826** | **71.23%** | **.1898703** |
| Handwritten offense/defense with EXISTING 20% venue | 1982 / 2826 | 70.13% | .1917676 |
| Handwritten, historical venue REMOVED (0%) | 1967 / 2826 | 69.60% | .1947521 |
| Handwritten, venue 10% | 1979 / 2826 | 70.03% | .1925307 |
| Handwritten, venue 30% | 1983 / 2826 | 70.17% | .1921764 |
| Handwritten, venue 40% | 1980 / 2826 | 70.06% | .1934971 |
| Handwritten, 20% venue + fixed **+0.10 home log-odds** | 1977 / 2826 | 69.96% | .1908329 |
| Handwritten, 20% venue + fixed **+0.20 home log-odds** | 1988 / 2826 | 70.35% | .1905925 |
| Handwritten, 20% venue + fixed **+0.35 home log-odds** | 1994 / 2826 | 70.56% | .1915066 |

**Interpretation:** Removing the production historical home/road adjustment worsened both accuracy and probability quality. Simply increasing its coefficient to 30% or 40% did NOT consistently improve either metric. An **additional constant +0.20 home log-odds adjustment** improved the handwritten model Brier score in this retrospective cohort, but still did not surpass unchanged production V1.5. The +0.35 fixed home adjustment produced the most handwritten correct picks (1994), but its Brier score was worse than +0.20, and it still trailed V1.5 by 19 games. These modifications change only venue and hold all remaining coefficients fixed rather than renormalizing them.

## Does home-field + handwritten both advantages overturn V1.5?

- When the **home team** had both handwritten statistical advantages but V1.5 picked the away team, there were just **22 games**: home handwritten selection went **11-11**, exactly the same as keeping V1.5.
- When the **away team** had both advantages but V1.5 picked the home team, there were **46 games**: V1.5 went **24-22**, following handwritten ratings went **22-24**.
- Those two groups together indicate no convincing incremental override benefit, consistent with the prior both-vs-V1.5 research.

## Recommendation

Do not change production V1.5 based on these historical tests. A descriptive **home + stronger handwritten offense + stronger handwritten defense** research flag merits future prospective tracking, but 81.4% historical straight-up accuracy does not imply positive ATS/ML value or beat V1.5's predictive probability. If later comparing betting selections, capture odds and spreads **before kickoff** and evaluate ROI separately.

### Caveats

All years are retrospective and already examined in prior research, public data can be revised, and only eligible complete earlier-week games are included. The conditional home/away comparisons involve different teams, so do not interpret the raw difference as the causal effect of home field. Predetermined coefficient tests are exploratory, not fresh blind holdouts. For any promotion, lock predictions prospectively and compare on identical games.

Re-run: `PYTHONPATH=. python research/handwritten_offense_defense_2026_10_12/home_field.py`. Data: `home_field_results.json`. Tests: `tests/test_handwritten_home_field.py`. GitHub Actions completed successfully. Changes are isolated to the research branch.
