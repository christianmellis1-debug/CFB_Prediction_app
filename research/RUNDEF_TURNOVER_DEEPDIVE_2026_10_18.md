# Run-defense + turnover advantage: Deep-dive and home-underdog controls
Date: 2026-10-18. Research branch only, **no production modification**.

## Definition
Home team has two positive pregame Saturday Forecast statistics: lower rushing yards per carry allowed than the away team, and higher prior-week FBS turnover margin (takeaways minus giveaways per game) than the away team. All 2024–2026 comparisons FBS vs FBS, P4/P4 or G6/G6, nonneutral, metric computed from prior-week games only. The game outcome is the **home** side covering an ESPN-derived retrospectively archived spread, which can differ from a frozen original line.

**Crucial:** Tier 1 6/6 already contains both positive flags. This pair by itself cannot filter Tier 1 losing selections. Its use would be alternative selection among teams with fewer positive metrics.

## Full historical result and idealized hypothetical ROI
Assume a hypothetical flat $10 bet per event at an identical -110 price, every qualifying event available at its archived line, pushes void. This is **not realized profit** and does not include actual historical prices, access/slippage, fees, or selection timing.

| Season | Both signals ATS | Rate | Hypothetical $10-bet P/L |
|---|---|---:|---:|
| 2024 | 90–79 | 53.3% | +$28.18 |
| 2025 | 88–77 | 53.3% | +$30.00 |
| 2026 W1–7 | 37–30–1 | 55.2% | +$36.36 |
| **Combined** | **215–186–1** | **53.6%** | **+$94.55** |

At -110 break-even is 52.38%; the overall 53.6% barely exceeds that threshold. Week 7 2026 alone: pair 7–11 ATS; six-of-six subset 3–7.

Pair vs no pair across three seasons: 215–186–1 (53.6%) versus 514–504–4 (50.5%). However pair games were typically far more favored: mean home spread -10.36 and +198 pregame Elo, versus mean +0.65 and -82 Elo for no pair. This confounds naive comparisons.

## Conference groups

| Group | Both flags record | ATS win% | -110 hypothetical ROI |
|---|---:|---:|---:|
| P4 vs P4 | 106–100 | 51.5% | -1.8% |
| G6 vs G6 | 109–86–1 | 55.9% | +6.7% |

Year-by-year P4 37–41, 48–40, 21–19; G6 53–38, 40–37, 16–11–1. No stable opportunity across all subgroups.

## Point-spread bands for home pair

| Home side line | ATS result | Win% |
|---|---:|---:|
| Fav -14 or more | 72–71 | 50.3% |
| Fav -7 through -13.5 | 48–42 | 53.3% |
| Fav -0.5 through -6.5 | 58–53 | 52.3% |
| **Home underdog** | **37–20–1** | **64.9%** |

The home underdog pair had 12–9 (57.1%) in 2024, 19–7 (73.1%) in 2025, and 6–4–1 (60.0%) in 2026. There were **no pick'em games in this candidate**, so this is strictly home underdogs.

However the whole 3-year home underdog pool was 297–277–1 (51.7%), and the unflagged home underdogs were 260–257 (50.3%). Pair teams had mean underdog spread +4.23, versus +8.80 among unflagged underdogs; they were materially more competitive, so conditional comparison must account for market/Elo.

In fixed cells of season + conference group + underdog spread band (0–3.5, 4–7.5, 8+) + Elo band, the flagged home underdogs outcovered comparables by **+23.5 percentage points** using 55 of 57 graded flagged dogs on shared support. This is **highly exploratory**: most individual cells have only 1–4 flagged games, and this underdog rule was identified after scanning spread groups.

A regularized walk-forward logistic probability audit conditioned on home underdogs and accounting for home spread, Elo, week and conference found:
| Holdout | Controls only Brier | Plus run defense+turnover flag | Delta |
|---|---:|---:|---:|
| 2025, trained 2024 | 0.26198 | 0.26001 | -0.00197 (small gain) |
| 2026, trained 2024–25 | **0.24742** | 0.24747 | +0.00005 (no gain) |

Against the constant 0.25 Brier benchmark, both models underperformed in 2025; 2026 pair did not beat controls. The 2026 forward-projection coefficients are positive, but incremental held-out probabilities are not demonstrably improved.

## Magnitude study: do larger positive edges help?

A priori historical median cutoffs calculated on the earlier-year flagged pairs:
- Train 2024, test 2025: run-def difference >=1.002 YPC and turnover-margin difference >=1.000 per game. Pair baseline 88–77 (53.3%). Above both medians **20–19 (51.3%)**. Below both medians **30–18 (62.5%)**.
- Train 2024–25, test 2026: run-def difference >=0.987 YPC, turnover-margin difference >=0.979 per game. Pair baseline 37–30–1 (55.2%). Above both medians **15–13 (53.6%)**, below both **7–7–1 (50%)**.
- Bigger gaps in both metrics did not consistently improve cover selection. No magnitude threshold supported for deployment.

## Original Elo spread-value cross-check

Independent home winning-margin linear Elo forecast fit entirely on past-year same-group matches with verified pregame metrics.

| Holdout | All pair ATS | Pair with positive Elo spread value | Pair requiring >= +3 pts value |
|---|---:|---:|---:|
| 2025, train 2024 | 88–77 (53.3%) | 44–40 (52.4%) | 24–16 (60%), n40 |
| 2026, train 2024–25 | 37–30–1 (55.2%) | 19–17 (52.8%) | 16–13 (55.2%), n29 |

No consistent gain from imposing a simple positive Elo spread edge. A +3 cutoff is post-hoc and unstable at low n, cannot validate pair or Elo screen.

## Another retrospective pattern: exactly three of five advantages
Under the two mandatory positives (run defense + turnovers), and exactly one of the other three matchup advantages (total = 3 of 5):
- 2024 29–9 (76.3%), 2025 21–16 (56.8%), 2026 9–6–1 (60.0%); pooled **59–31–1 (65.6%)**.
- Pair with four of five advantages: 44–59 (42.7%) across 2024–2026.
- Pair with all five: 101–91 (52.6%).
- These splits are retrospective post-hoc comparisons discovered while studying the same data. The 3/5 group is highly confounded by spread size (mean home spread -5.98 versus -14.53 for all five) and selection bias. Do not introduce a new tier without an independent forward holdout.
- Home-underdog 3/5 intersection itself was 18–7–1 (72.0%), and 2026 only 3–3–1. This should **not** be optimized further on the same matches.

## Decision
The run-defense+turnover pair is a promising **qualitative matchup flag**, especially for competitively priced home underdogs. It is **not yet an independently validated ATS strategy**:
1. Just 57 decided home-underdog games over 3 years, and the standout subgroup was found retrospectively.
2. Pair already present in Tier 1, so cannot by itself repair existing Tier 1.
3. No reliably improved controlled 2026 probability score.
4. Magnitude-threshold and positive Elo-spread-value combination did not improve consistency.

Keep production rules unchanged. If conducting prospective research, freeze the *home underdog + both flags* definition and odds before kickoff, measure against contemporary sportsbook line and unflagged underdogs in corresponding spread/Elo categories over untouched future weeks, and grade using actual prices. Treat the exactly-3-of-5 flag as a separately named and **post-hoc** future exploration, with adequate sample before decisions.

Research files:
- `tests/test_rundef_turnover_deepdive_2026_10_18.py`
- `tests/test_rundef_turnover_underdog_control_2026_10_18.py`
Both standalone historical investigations passed (GitHub Actions runs 39142949601 and 39143190136); unrelated previously failing UI copy expectations cause failures in broad regression suite. No main deployment.
