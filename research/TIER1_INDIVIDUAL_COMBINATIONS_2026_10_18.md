# Saturday Forecast: individual matchup advantages and combinations, controlled ATS study
Date: 2026-10-18. **Research-only; no production model or tier modifications.**

## Scope and reproducibility

Used `matchup_advantages.build_advantages` and `assess` unchanged for regular-season FBS-vs-FBS, same P4/P4 or G6/G6 nonneutral games. Computed pregame advantages using strictly earlier-week box scores, and settled home-side ATS against ESPN-derived archived market spreads. Five binary indicators:

1. Run matchup: team projected rushing YPC versus opponent defensive rushing YPC.
2. Pass matchup: offensive completion percentage versus opposing completion percentage allowed.
3. Run defense: comparative rushing YPC allowed.
4. Pass defense: comparative completion rate allowed.
5. Turnover margin: comparative prior-week FBS takeaways-minus-giveaways per game.

Picks are *home-side research observations*, not the production tier priority or actual placed bets. There are 1,424 games with complete metrics, pregame Elo and archived spreads (2024 n=569, 2025 n=595, 2026 n=260); 1,419 had a decided ATS win/loss and 5 pushes. Coverage of fully evaluated pregame 5-metric FBS games: 2024 571 with 2 unpriced; 2025 595; 2026 260. Historical market values are archived, not necessarily immutable original kickoff quotes. P4/G6 grouping follows existing code, including Notre Dame treatment.

Each of 5 single signals, 10 pair combinations, 10 triple combinations, plus all 5 main effects and full interaction model, was tested. Controlling model includes **signed/absolute sportsbook home spread, signed/absolute pregame Elo difference, week, P4/G6**, with fixed ridge penalty 8. All 2025 model coefficients trained on 2024 games; all 2026 coefficients trained on 2024+2025, never on same-season results. Primary held-out metric is Brier probability error, lower better, market-neutral 0.250.

## Single-advantage ATS record (raw, no controls)

| Advantage present | 2024 | 2025 | 2026 | Pooled |
|---|---|---|---|---|
| Run matchup | 143-141 (50.4%) | 149-136 (52.3%) | 66-55-4 (54.5%) | 358-332-4 (51.9%) |
| Pass matchup | 148-158 (48.4%) | 148-136 (52.1%) | 62-66-2 (48.4%) | 358-360-2 (49.9%) |
| **Run defense** | **149-126 (54.2%)** | **155-137 (53.1%)** | **62-59-1 (51.2%)** | **366-322-1 (53.2%)** |
| Pass defense | 138-157 (46.8%) | 149-144 (50.9%) | 58-60-1 (49.2%) | 345-361-1 (48.9%) |
| Turnover margin | 139-137 (50.4%) | 146-130 (52.9%) | 62-53-2 (53.9%) | 347-320-2 (52.0%) |

Across all matchups, overall home ATS rate = 729-690-5 (51.37%). These cohorts overlap extensively. Run defense has the strongest pooled 53.2% observational rate, but a single run-defense flag makes held-out Brier score worse **in 2025 and 2026**.

## Prespecified review of meaningful two- and three-way combinations

| Both/All home advantages present | 2024 ATS | 2025 ATS | 2026 ATS | Pooled ATS |
|---|---|---|---|---|
| **Run defense + turnover margin** | **90-79 (53.3%)** | **88-77 (53.3%)** | **37-30-1 (55.2%)** | **215-186-1 (53.6%)** |
| Run matchup + turnover margin | 91-89 (50.6%) | 86-74 (53.8%) | 41-33-2 (55.4%) | 218-196-2 (52.7%) |
| Run matchup + pass defense | 80-90 (47.1%) | 90-80 (52.9%) | 37-28-1 (56.9%) | 207-198-1 (51.1%) |
| Pass matchup + turnover margin | 87-97 (47.3%) | 87-84 (50.9%) | 37-40-1 (48.1%) | 211-221-1 (48.8%) |
| Run matchup + pass defense + turnover margin | 56-62 (47.5%) | 57-46 (55.3%) | 26-20 (56.5%) | 139-128 (52.1%) |

**Run defense + turnover margin** was the best pair from 2024–25 after screening combinations with at least 40 earlier-year games; its untouched 2026 historical evaluation was 37–30 (55.2%). That is a sensible *shadow monitoring* candidate, but only 67 nonpush games were available in 2026. The selected 2024–25 success rate was only 53.3%, barely above -110 ATS break-even (~52.38%), and selection across 10 pairs creates multiple-testing risk.

## Controlled out-of-year predictive accuracy

| Holdout | 50% constant Brier | Spread/Elo/week/group baseline | All five main indicators | Full five-indicator interaction model |
|---|---:|---:|---:|---:|
| 2025 (trained 2024; n=595) | **0.25000** | 0.25523 | 0.25608 | 0.25545 |
| 2026 (trained 2024-25; n=255 nonpush) | 0.25000 | 0.24785 | 0.24824 | **0.24596** |

Adding the five binary indicators alone **worsened the baseline in both holdout seasons**, with Brier change +0.000846 and +0.000393 respectively. Allowing all 2- through 5-way interactions helped the 2026 Brier modestly (-0.001886 vs the control-only model), but still worsened it slightly in 2025 (+0.000222) and did not beat a 0.25 constant baseline that year. This larger 38-parameter model is exposed to overfitting and is not a reliable tier upgrade.

Selected individual indicators' incremental Brier impact relative to spread/Elo/week/group baseline:
- **Run defense:** 2025 +0.000499 (worse); 2026 +0.001446 (worse).
- **Turnover margin:** 2025 -0.000015; 2026 -0.000210 (tiny improvements).
- **Pass defense:** 2025 +0.000363 (worse); 2026 -0.000994 (improved), with **negative** fitted coefficients meaning the flag predicted a lower chance of a home cover conditional on line/Elo.
- **Run matchup:** 2025 +0.000078 (worse); 2026 -0.000420 (improved).
- **Pass matchup:** 2025 +0.000008 (worse); 2026 -0.000320 (improved).

Selected pair models (two separate indicators added; not necessarily synergy):
- Run defense + turnover: 2025 +0.000488, 2026 +0.001222 (both **worse**, despite raw cover rates).
- Run matchup + pass defense: 2025 +0.000440 (worse); 2026 -0.001419 (better). Its raw home ATS performance went 47.1% -> 52.9% -> 56.9%; no year-to-year consistency established.
- Pass matchup + turnover: 2025 -0.000019, 2026 -0.000622 (tiny held-out improvements). A model with a true pairwise interaction versus two main effects improved both years, -0.000346 and -0.000624, but fitted interaction coefficients were **negative**, indicating this pair may be an overvalued favorite/reverse-side warning rather than a new home-side pick; raw pair covers were 47.3%, 50.9%, 48.1%. Multiplicity means these improvements are speculative.
- Pass matchup + pass defense: true interaction vs main effects changed Brier by -0.000354 in 2025 and -0.000197 in 2026 (marginal).

## Conclusions

1. **Run defense** has the best raw individual ATS association (53.2% pooled), but no demonstrated incremental out-of-year predictive value after controlling for sportsbook prices and Elo.
2. **Run defense + turnover-margin advantage** is the most consistent straightforward historical win-rate combination (53.3%, 53.3%, 55.2%), *not* a proven profit edge or a validated predictive improvement. The adjusted pair model worsened both held-out Brier scores. Do not promote it.
3. **Pass defense** potentially has a counterintuitive *negative* cover association conditional on sportsbook spread, especially in 2026, but it is unstable in 2025 and should not be treated as a fade rule without direct side-specific prospective testing.
4. Adding all five main effects does not improve held-out probabilities. Rich interactions slightly help 2026 but fail 2025, so model complexity is not justified.
5. Multiple combinations and retrospective lines mean apparent best patterns can arise by chance. Preserve current Saturday Forecast tier rules. Next research should use continuous *mismatch magnitudes* rather than binary signs, plus opponent adjustment, and compare with the simple Elo spread-value method on truly prospective line-locked weeks. Test prespecified families with no after-the-fact thresholds and realistic -110 economics.

## Artifact links
Standalone code `tests/test_tier1_individual_combinations_2026_10_18.py` on the research branch. GitHub Actions run 39142236719: the standalone study passed. Broader pre-existing app regression suite has unrelated stale UI-copy assertions, and was not repaired as part of research. Production main branch untouched.
