# Saturday Forecast — Test C: Confidence calibration and sportsbook disagreement

**October 13, 2026 — Research only.** Production model, confidence labels, betting waterfall, and app have not been modified.

## Reproducible design and source integrity

- **Prospective-source cohort:** `data/shadow_tracking.json` on main, 171 frozen pregame snapshots, 112 completed/verified with matching two-sided DraftKings moneylines, exactly 56 games each in 2026 Weeks 5 and 6. The remaining 59 were unsettled and excluded. Capture times were verified before the listed kickoff. Book quotes were captured before kickoff, but not necessarily at closing.
- Convert both American moneylines from the **same sportsbook** to implied probabilities and normalize their sum to one (remove overround). Verify exact agreement with the no-vig pick-side probability already stored in each frozen snapshot. Score home-win probabilities and final outcomes on matching event IDs.
- **Historical confidence context:** 2024 (752 games) and 2025 (762 games), current V1.5 retrospectively reconstructed against historical weekly summaries saved in the [Test B research](https://github.com/christianmellis1-debug/CFB_Prediction_app/tree/research/test-b-venue-calibration-2026-10-13/research). These years **do not have matching verified historical sportsbook moneylines** in this experiment and cannot support historical model–market disagreement claims. Published feeds can revise historical metrics.
- Blends tested as `P(home) = model_weight × V1.5_home_probability + (1-model_weight) × no_vig_market_home_probability`. We evaluate the recalculated **winner and probability**. This is **distinct** from the existing shadow tracker, which fixes the original predicted winner for its value-bet comparison.
- Thresholds and candidates are investigated retrospectively on 2026 outcomes, not preregistered or validated on genuinely unseen weeks. Week 5 and Week 6 are diagnostic splits, **not** independent holdouts for thresholds chosen from all results.
- Lower Brier score / log loss is better; there are no ATS, ROI or profitability claims.

## C1 — Accuracy and confidence calibration

| Period | Winner record | Avg model confidence | Brier | Log loss |
|---|---:|---:|---:|---:|
| 2024 reconstructed | 536–216, 71.28% | 73.14% | 0.187913 | 0.552196 |
| 2025 reconstructed | 546–216, 71.65% | 71.84% | 0.183029 | 0.538663 |
| 2026 weeks 5–6 frozen | 77–35, 68.75% | 71.47% | 0.208983 | 0.606358 |

On the frozen 2026 cohort:

| V1.5 confidence band | n | Actual pick wins | Accuracy | Mean predicted confidence |
|---|---:|---:|---:|---:|
| 50–60% | 31 | 17 | 54.8% | 55.5% |
| 60–70% | 22 | 16 | 72.7% | 66.3% |
| 70–80% | 27 | 18 | 66.7% | 75.9% |
| 80–90% | 24 | 19 | 79.2% | 84.4% |
| 90–100% | 8 | 7 | 87.5% | 93.8% |

The 70–80% band is off by approximately −9.2 percentage points in 2026; this is descriptive and does not establish globally miscalibrated confidence.

In 2024 the reconstructed 70–80% band won 118/165 (71.5%; mean confidence 74.8%) and the 80–90% band 121/150 (80.7%; mean 85.0%). In 2025 they won 107/147 (72.8%; mean 75.2%) and 110/131 (84.0%; mean 85.1%). The earlier seasons show smaller and less consistent gaps than the early 2026 sample.

## C2/C3/C5 — Disagreement-warning candidates

On the 112 frozen games, market favorite and V1.5 winner each finished 77–35 (68.75%), but the market had **better probability scores**:

| Score | V1.5 | No-vig sportsbook market |
|---|---:|---:|
| Brier | 0.208983 | **0.191311** |
| Log loss | 0.606358 | **0.559319** |

Week 5: V1.5 42–14; market 39–17. Week 6: V1.5 35–21; market 38–18.

| Warning definition | 2026 model W–L | Week 5 | Week 6 |
|---|---:|---:|---:|
| Market and model choose opposite winners | 10–10 (50.0%) | 6–3 | 4–7 |
| Model pick ≥70% / market same-side <55% | **1–4 (20.0%)** | 1–1 | **0–3** |
| Model pick ≥80% / market same-side <70% | 4–4 (50.0%) | 3–2 | 1–2 |
| Model confidence exceeds same-side market probability ≥15 points | 15–10 (60.0%) | 8–3 | 7–7 |
| Model confidence exceeds same-side market probability ≥20 points | **6–8 (42.9%)** | 3–2 | 3–6 |

Agreeing winner: 67–25 (72.8%). Opposing market winner: 10–10 (50.0%). Exploratory Fisher exact test two-sided p≈0.062; conventional statistical certainty is **not established**.

**The five strongest warning examples** under model pick ≥70% and same-side sportsbook probability <55%:
- Week 5: Pittsburgh at Virginia Tech; V1.5 72.6%, market 40.7%; V1.5 **correct**.
- Week 5: Army at Louisiana Tech; V1.5 80.3%, market 54.3%; V1.5 **wrong**.
- Week 6: USC at Penn State; V1.5 80.2%, market 46.8%; V1.5 **wrong**.
- Week 6: Sacramento State at Bowling Green; V1.5 76.4%, market 29.5%; V1.5 **wrong**.
- Week 6: Louisiana at Louisiana Tech; V1.5 79.9%, market 51.1%; V1.5 **wrong**.

These flags are **hypothesis generating** and should not be deployed as a proven betting filter. Flagging does not prove profit or guarantee failure.

## C4 — Market-assisted probability challenger

| Home-probability calculation | W–L / 112 | Accuracy | Brier |
|---|---:|---:|---:|
| V1.5 only | 77–35 | 68.75% | 0.208983 |
| 75% model + 25% market | 75–37 | 66.96% | 0.200418 |
| 50% model + 50% market | 78–34 | 69.64% | 0.194618 |
| 25% model + 75% market | 78–34 | 69.64% | 0.191582 |
| Previously defined 16.93% model + 83.07% market | **78–34** | 69.64% | **0.191192** |
| Market only | 77–35 | 68.75% | 0.191311 |

The 16.93% blend changed 17 original V1.5 picks, fixing nine and breaking eight, for **net +1 correct winner**. Its Brier advantage over market-only is approximately **0.000119**, effectively a tie on this cohort.

**Split by week:**
- Week 5: V1.5 42–14, market 39–17, previously defined blend 40–16.
- Week 6: V1.5 35–21, market 38–18, previously defined blend 38–18.

The blend's improvement in probability scoring does not establish improved future straight-up picks or betting profitability.

## Uncertainty

Descriptive 3,000-sample stratified-by-week game-level bootstrap (assumes games within a week independent; team effects may invalidate this precision):
- V1.5 Brier minus market Brier: **95% interval −0.0086 to +0.0451**, crosses zero.
- 16.93% blend Brier minus market Brier: **95% interval −0.0045 to +0.0042**, crosses zero.
- Blend accuracy minus baseline accuracy: **95% interval −6.25 to +8.04 percentage points**, crosses zero.

The sample **does not demonstrate statistically reliable superiority** of one winner-picking method over the other.

## Decision

1. **Keep V1.5 winner predictions and waterfall tiers unchanged.**
2. Retain the **≥70% V1.5 versus <55% no-vig market same-side probability** pattern as a shadow-tracked *high-priority disagreement alert* hypothesis only, not a proven betting selection or automatic change to confidence.
3. Continue the previously established 16.93% blend research, measuring both switched-winner accuracy and proper probability scores before deployment.
4. Prospective capture every qualifying game with provider, odds on both sides, kickoff timestamp, V1.5 probability, no-vig market probability, confidence band and warning categories. Validate warning precision and the model-blend on several future full weeks without changing thresholds.

## Reproduction

- `research/test_c_market_confidence.py` reads pinned internal archive and existing, commit-pinned historical V1.5 reconstruction.
- `research/test_c_results.json` contains all metrics, calibration bands, confidence-warning examples, split weeks and bootstrap intervals.
- `research/test_c_game_results.csv` stores matched 2026 game-level predictions and independently derived bookmaker probabilities.
- `.github/workflows/research-test-c.yml` runs this research independently on the dedicated branch.

**Source links:** [frozen prediction archive](https://github.com/christianmellis1-debug/CFB_Prediction_app/blob/main/data/shadow_tracking.json), [Test C research branch](https://github.com/christianmellis1-debug/CFB_Prediction_app/tree/research/test-c-market-confidence-2026-10-13/research).
