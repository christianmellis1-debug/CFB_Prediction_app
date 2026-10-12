# Competitive-spread magnitude test: selected home team spread > −10

**2026 Week 3–6 40/25/15/10/10 hypothetical handwritten model. No production or official tier changes.**

## Exact rule

- Selected team is at home (not neutral).
- Selected team has BOTH a strictly higher pregame offense rating and a strictly higher defense rating, under the handwritten internal weights 40% EPA / 25% rushing / 15% passing / 10% turnovers / 10% explosive plays, with current V1.5 preseason blend.
- Only historical sportsbook **point spreads strictly greater than −10** for selected home team: e.g. −9.5, −7, −3, +2.5. A spread exactly −10 is excluded.
- Magnitude is the **smaller** of the two positive rating gaps. Nonoverlapping analysis groups are 0–0.24, 0.25–0.49, 0.50–0.74, and 0.75+. These are standardized rating units, NOT % or points.

### 2026 Weeks 3–6

| Magnitude band | Qualifying games | SU record | SU win rate | Avg. home spread |
|---|---:|---:|---:|---:|
| 0–0.24 | 9 | 5–4 | 55.6% | −2.5 |
| 0.25–0.49 | 7 | 6–1 | 85.7% | −5.5 |
| 0.50–0.74 | 6 | 3–3 | 50.0% | −4.9 |
| 0.75+ | 4 | 3–1 | 75.0% | −7.1 |
| **Total** | **26** | **17–9** | **65.4%** | **−4.6** |

Cumulative, with magnitude >=0.25: **12–5 (70.6%)** across 17 games; >=0.5: **6–4 (60.0%)** across 10 games; >=0.75 **3–1 (75.0%)** across 4 games.

### 2023–2025 historical comparison (same rules; 2022 spread data inadequate)

| Magnitude band | Games | SU record | SU win rate | Avg. spread |
|---|---:|---:|---:|---:|
| 0–0.24 | 108 | 67–41 | 62.0% | −4.3 |
| 0.25–0.49 | 71 | 46–25 | 64.8% | −5.8 |
| 0.50–0.74 | 16 | 12–4 | 75.0% | −7.0 |
| 0.75+ | 6 | 4–2 | 66.7% | −5.0 |
| **Total** | **201** | **129–72** | **64.2%** | **−5.1** |

2023–2025 cumulative magnitude >=0.25: **62–31 (66.7%)** across 93 games. Original 2026 strong 6–1 record in the 0.25–0.49 group is **not stable** enough to promote as a guaranteed tier signal. In 2023 that band was 13–9, in 2024 21–7, in 2025 12–9.

### Narrower favorite market control

To avoid comparing favorites to underdogs, restrict further to **home favorites only**, spread in (−10, 0). Also compare only against **other home favorites** in the same years and signed spread groups of [−3,0), [−7,−3), (−10,−7). Use the qualification count in each spread group as the weight in the comparison.

| Period | Both-edge home favorites | Other home favorites, unadjusted | Other favorites standardized for the rule's spread mix |
|---|---:|---:|---:|
| 2026 W3–6 | **17/24 = 70.8%** | 30/46 = 65.2% | **69.9%** |
| 2023–2025 | **118/181 = 65.2%** | 295/470 = 62.8% | **68.4%** |

2026 difference after three-bin market-spread adjustment = **+0.9 percentage points** and historical 2023–25 difference = **−3.3 points**. Both comparisons are small-sample descriptive comparisons, not significance-tested or a fully calibrated model, so neither establishes market-beating predictive value. The 2026 data includes **two home underdogs** satisfying the condition (Maryland +2.5; Massachusetts +6), and **both lost**; they are included in the 26 total but excluded from favorite-only comparators.

### Interpretation

A rule excluding magnitude <0.25 has a modest 2026 improvement (12–5 versus 17–9 overall), but this does not replicate strong enough in 2023–25 to justify declaring it profitable or granting official tier status. Within a spread >−10, magnitude is **not monotonically predictive in 2026**: the 0.50–0.74 group went just 3–3. At 0.75+, the cohort is only 4 games in 2026, 6 games in 2023–25.

These are **straight-up winners**, not ATS bets or moneyline ROI. Historical spread sourced from ESPN-derived archived 2023–2026 files, not a prospectively locked DraftKings line. The selected game population is restricted to earlier-week complete FBS box histories (Weeks 3+) and reconstructed historical ratings. Model is not live.

**Recommendation:** Keep a purely research-only magnitude+spread candidate and lock forward results before adding a waterfall tier. If the priority is genuinely tradable moneylines, evaluate the no-vig implied winner probability / price and ROI against the archived same-game odds; heavy-favorite selection in broader groups had inflated straight-up win rates.

Source game-level cohort: `research/handwritten_offense_defense_2026_10_12/home_field_ats_games.csv` in branch `research/handwritten-home-field-ats-2026-10-12`. All values reproducible from `season`, `week`, `both_side`, `neutral_site`, `home_team_spread`, `home_points`, `away_points`, `proposed_offense_edge`, and `proposed_defense_edge`.
