# Saturday Forecast — Test C/V1.5 Small-Weight Sensitivity, 2026 Weeks 3–6

**October 13, 2026 — Research only. Production Test C 16.9279269% / 83.0720731% and V1.5 35/35/20/10 weights remain unchanged.**

## Identical historical cohort and caution

221 FBS matchups with authentic-source archived two-sided DraftKings **opening** odds: Week 3=53, Week 4=56, Week 5=56, Week 6=56. Results use fixed no-vig market prices and event ID joins. V1.5 Weeks 3–4 are retrospectively reconstructed with historical weekly summaries; Weeks 5–6 use original locked before-kickoff V1.5 probabilities. Alternative V1.5 shifts for Weeks 5–6 are retrospectively estimated log-odds deltas, added to original frozen V1.5 probabilities, **not actual pregame predictions from those alternate models**. The odds archive may have later revisions without independently audited timestamps. This retrospective comparison cannot show independent future improvement.

## Part 1 — Shift Test C top-level weights by up to 5 points

`P(home) = w × V1.5 + (1-w) × DraftKings no-vig`.

| Model share | Market share | Correct / 221 | Brier (lower better) |
|---|---|---|---|
| 11.93% | 88.07% | 168 | 0.169966 |
| 14.93% | 85.07% | 169 | 0.170062 |
| 15.93% | 84.07% | 169 | 0.170103 |
| **16.93% current** | **83.07%** | **169** | **0.170147** |
| 17.93% | 82.07% | 169 | 0.170195 |
| 18.93% | 81.07% | 169 | 0.170247 |
| 21.93% | 78.07% | 168 | 0.170428 |

Within **±2 percentage points**, all winner picks are **identical** to current Test C: 169–52, **76.47%**. More weight on sportsbook slightly helps Brier on this cohort, but effect is tiny and selecting weights on outcomes is overfitting. At ±5 points, each extreme breaks one formerly correct Week 5 pick and corrects none.

## Part 2 — 24 small V1.5 component reallocations

Base independent V1.5: **35% offense, 35% defense, 20% venue, 10% schedule strength**. Exactly 24 configurations: transfer either **1 or 2 percentage points** from any one of four components to any other (six pairs, both directions, two sizes), keeping total exactly 100 points. All else held constant (confidence calibration, prior/current season mix, conference correction, model/market 16.93/83.07 split).

| V1.5 offense / defense / venue / SOS | Test C W–L / 221 | Brier |
|---|---|---|
| **35 / 35 / 20 / 10 (production)** | **169–52** | 0.170147 |
| 36 / 34 / 20 / 10 | **169–52** | 0.170075 |
| **37 / 33 / 20 / 10 (best Brier)** | **169–52** | **0.170003** |
| 35 / 33 / 20 / 12 | **169–52** | 0.170043 |
| 37 / 35 / 18 / 10 | **169–52** | 0.170084 |
| 33 / 37 / 20 / 10 | 167–54 | 0.170293 |

**No candidate outperformed the existing model's 169 winners.** The best probability candidate 37/33/20/10 improved Brier by merely **0.000144**, ~0.085% relative, and made **zero different final winner predictions**. Conversely, shifting two points from offense to defense produced two additional wrong final winners, both from Week 5.

The current Test C baseline per week: W3 45–8, W4 46–10, W5 41–15, W6 37–19. Best Brier candidate and most alternatives retain **all four weekly winner records**; thus no evidence any micro-weight adjustment fixes Week 6's accuracy slump.

Some V1.5-only probabilities did change, but Test C is ~83% market-sourced, so those changes seldom cross the 50% threshold for the final favorite. This is expected, not proof the individual metrics have no value.

## Decision

**Do not change production weights** on this retrospective sensitivity test. The most promising micro-change (37/33/20/10) preserves all 169 correct Test C picks and only marginally changes confidence scoring. Test it independently over 2024/2025 full seasons or on newly frozen future games rather than treating a ~0.00014 Brier difference on 221 already-reviewed games as a reliable gain.

## Artifacts

- `research/weight_micro_w3w6.py` reproducible model reruns.
- `research/weight_micro_w3w6_results.json` 25 weights, matched accuracy/Brier/log loss, Week 3–6 splits, frozen split, changed pick accounting, and independent V1.5 metrics.
- `research/weight_micro_w3w6_games.csv` per-game predicted home probabilities under all 25 candidate component configurations.
- `.github/workflows/research-weight-micro-w3w6.yml` completed successful isolated workflow.

This file is on the research branch only. No changes to the live app, published model weight constants, or betting waterfall.
