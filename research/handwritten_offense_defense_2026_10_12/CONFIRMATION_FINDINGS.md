# Handwritten offense + defense confirmation vs V1.5 (October 12, 2026)

**Research-only, exact same games and originally specified 40/25/15/10/10 ratings. No live model weights, predictions, or Value tiers modified.**

## Question

When both of the proposed offensive and defensive ratings prefer one team, is that information **incrementally useful beyond original V1.5**?

Specifically, compare V1.5 against a prespecified hypothetical override: if the proposed offense and defense BOTH favor the same team but that conflicts with the predicted V1.5 winner, flip to the proposed team. In all other cases, keep V1.5 unchanged. Also examine selecting only games where both proposed ratings agree with V1.5, and benchmark the **original V1.5 unit ratings** on the exact same eligible schedule.

The proposed offense/defense unit differences are constructed from the same prior-season Elo/efficiency prior and current-season handwritten weights as the earlier A/B test. This analysis validates exact parity with the earlier A/B score changes. It never examines final scores before identifying candidate conditions.

## Key paired results, 2,826 eligible games (2022-2026 through W6)

| Condition / strategy | W-L | Hit rate | Coverage |
|---|---:|---:|---:|
| Original V1.5 all eligible games | 2013-813 | 71.2% | 2826 |
| V1.5 plus proposed two-unit override | 2009-817 | 71.1% | 2826 |
| Proposed offense AND defense both prefer same team | 1265-415 | 75.3% | 1680 |
| **Proposed both units agree WITH V1.5 winner** | **1232-378** | **76.5%** | **1610** |
| Proposed both units disagree WITH V1.5: **V1.5's actual result** | 37-33 | 52.9% | 70 |
| Proposed both units disagree WITH V1.5: **proposed team's result** | 33-37 | 47.1% | 70 |
| Proposed offense and defense disagree with EACH OTHER: V1.5 result | 744-402 | 64.9% | 1146 |
| Original V1.5 unit ratings both agree with its own winner | 1165-337 | 77.6% | 1502 |

A high conditional 76.5% hit rate for the 1610 V1.5-confirmed games is a **selection effect**: those are still V1.5 predictions on a subset. It must not be portrayed as proof the proposed weights improve the original forecast. In this same cohort, the ORIGINAL-unit V1.5 confirmation had 77.6% hit rate but on a different 1502-game subset. There are only 70 true handwritten-versus-V1.5 conflicts.

**Flipping the 70 disagreements:** 33 earlier misses fixed, 37 previously correct wins lost = net **4 fewer correct winners**. Original-unit confirmation would have produced 9 gains and 24 losses over 33 conflicts (even worse); neither should trigger a production override.

## Paired year records

| Year | V1.5 all | Rule: flip on proposed two-unit conflict | Difference |
|---|---:|---:|---:|
| 2022 | 431/630 | 425/630 | -6 |
| 2023 | 474/646 | 477/646 | +3 |
| 2024 | 470/659 | 466/659 | -4 |
| 2025 | 474/663 | 478/663 | +4 |
| 2026 W3-W6 | 164/228 | 163/228 | -1 |

## Confidence subsets: only the 70 true conflicts

| V1.5 confidence | Conflicts | V1.5 | Proposed BOTH |
|---|---:|---:|---:|
| 50-59% | 57 | 28-29 | 29-28 |
| 60-69% | 10 | 8-2 | 2-8 |
| 70-79% | 3 | 1-2 | 2-1 |
| 80%+ | 0 | None | None |

The 50-59% bucket had one extra correct call for proposed BOTH, but 57 observations across already-examined seasons is **not** enough to conclude prospective advantage; other buckets favor keeping V1.5, and none of the observed conflicts involved V1.5's >=80%-confidence games.

A "veto" that abstains on the 70 conflicting games leaves V1.5 at 1976/2756 (71.7%), only 0.5 pp above its 2013/2826 (71.2%) full-cohort rate but at lower coverage. This does not establish odds-based ROI. It simply avoids 70 harder decisions, including 37 picks V1.5 had right.

## Illustrative 2026 conflicts

- Cincinnati at Arizona (Week 5): V1.5 Arizona, both handwritten ratings Cincinnati; **Arizona won**.
- California at UNLV (Week 5): V1.5 California, handwritten both UNLV; **UNLV won**.
- UCF at Oklahoma State (Week 6): V1.5 Oklahoma State, handwritten both UCF; **Oklahoma State won**.

## Decision

No change to production V1.5; a compulsory override is not warranted. The distinct rating's most promising role is an optional **confidence/confirmation research flag**, subject to prospectively frozen testing. The pure confirmation subset's 76.5% should **not** be sold as a novel predictive accuracy gain.

Limitations: all historical periods have been examined before; stats are reconstructed from retrospectively accessible earlier-week archives; schedules and advanced metrics can be revised; sample excludes incomplete earlier-week box histories and Weeks 1-2; this evaluates straight-up winners, not ATS, ML, profitability or calibrated model updates.

Code: confirmation_vs_v15.py. Complete machine-readable breakdown: confirmation_vs_v15_results.json. Unit tests: tests/test_handwritten_confirmation.py. Runs on independent research branch.
