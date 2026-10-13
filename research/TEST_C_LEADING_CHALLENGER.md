# Saturday Forecast — Test C leading prediction challenger

**Status: selected as the leading shadow prediction challenger, not approved as the production model.**
**Decision date:** October 13, 2026.

## Locked challenger definition

For each eligible FBS matchup with one sportsbook's valid two-sided pregame moneylines, derive the no-vig home-win probability:

`P_market(home) = implied(home_moneyline) / (implied(home_moneyline) + implied(away_moneyline))`

**Test C home-win prediction:**

`P_TestC(home) = 0.16927926947215113 * P_V1.5(home) + 0.83072073052784887 * P_market(home)`

- Test C chooses **home** if the resulting probability is at least 50%, otherwise **away**.
- Test C's confidence is the selected team's probability, `max(P_TestC(home), 1-P_TestC(home))`.
- The challenger is allowed to disagree with (and switch winners relative to) V1.5. That is precisely what we are prospectively testing.
- These coefficients are frozen until a new versioned research experiment. No tuning from subsequent outcomes.
- Never replace missing odds with invented prices, mix books across teams, capture after kickoff, or backfill a historical game as though captured contemporaneously.

## Why it is leading

In the matched **2026 Weeks 3–6** retrospective comparison (221 games), the challenger went **169–52 (76.47%)** versus V1.5 **158–63 (71.49%)**. It changed 29 winners, correcting 20 misses while introducing nine errors, net **+11 correct winners**. Brier: **0.170147** versus **0.187794**. This is useful exploratory evidence, not proof of future superiority.

Limitations: Weeks 3–4 were historical V1.5 reconstructions, Weeks 5–6 were frozen pregame V1.5 predictions, and the historical odds were archived opening prices without independently verified quote timestamps. A paired accuracy test for the 29 changed games yielded approximately p=0.061. Neither this experiment nor earlier market disagreement tests justify a live model switch by themselves.

**Past 2026 Weeks 5–6 frozen same-quote records, as captured before kickoff:**
- V1.5 **77–35 (68.75%)** versus Test C **78–34 (69.64%)** on 112 games.
- Test C changed 17 winners (nine fixes; eight new errors).
- Brier **0.208983** V1.5 vs **0.191192** Test C.
These numbers use originally archived moneylines, not later historical open/close prices.

## Prospective head-to-head now tracked

The existing six-hour GitHub Actions pregame capture (`.github/workflows/shadow-tracking.yml`) locks the **first available eligible pregame** observation no more than seven days before kickoff. Existing `data/shadow_tracking.json` snapshots already contain immutable:
- Game ID, opponent team IDs/names, game week, observed time and kickoff time
- Original V1.5 winner, side, chosen-team probability and provenance hashes
- Same-book two-sided moneylines (DraftKings preferred), bookmaker identifier, no-vig probability of the chosen side
- Frozen 16.93%/83.07% chosen-side blended probability

The new **prediction challenger** head-to-head in `shadow_tracking.winner_comparison` derives each method's *own winner* from the locked probabilities and evaluates the identical completed-game cohort on:
- Correct/incorrect straight-up winners, pick accuracy, Brier score, log loss
- Number of winner switches, wrong baseline picks corrected, correct baseline picks newly broken
- Matchup-level winner choices for individual game review
- Whole-season or individual-week matching scope, with pending games excluded

The pre-existing `comparison()` metric remains intact, measuring **fixed original-side hypothetical value bets**. It is explicitly displayed separately to avoid conflating a value-bet scenario that retains V1.5's winner with the new challenger that is allowed to switch sides. Production V1.5 winner calculation, confidence bands and all six betting tiers stay unchanged.

## Preregistered considerations before any production replacement

Only games newly and immutably captured **after formal challenger promotion** qualify for the primary forward-evaluation period. The archived 2026 Weeks 5–6 games are a replay/regression check, not new evidence. Before even considering deployment, inspect:

1. **Coverage:** A minimum of four future full weekly slates and at least 200 qualified, completed, identical-game captures, documenting any games excluded for missing prices.
2. **Winner quality:** Net positive winner accuracy versus V1.5 and evidence that the lift is not entirely from a single anomalous week. A practical target is at least **+2 percentage points** on the matched cohort; this is an evaluation target, not statistical proof.
3. **Probability quality:** Brier score improves by at least **0.005** and log loss does not regress; check calibration in the 50–60, 60–70, 70–80, 80–90 and 90+ confidence bands.
4. **Uncertainty:** Use paired game-level exact tests for changed winners and week/team-aware confidence intervals where feasible; clearly disclose if intervals still include zero.
5. **Football-specific failure modes:** Check Week 5–8 stability, Power 4 versus Power 4 and other groupings, heavy favorites, market disagreement, underdogs, venue, FCS exclusions, neutral sites, unpriced games, and late market movements.
6. **Betting integrity:** Do not reuse market-implied probabilities as independent evidence of a value edge against the **same** bookmaker price. If model predictions eventually change, evaluate waterfall tiers, expected value and moneyline selections separately rather than assuming a market-dominated forecast generates bettable edges.

**Fail-safe:** If no valid two-sided quote exists or the price is stale, retain the independent V1.5 winner for the live app; for the *head-to-head*, exclude the game from the matched market-eligible sample and report the missing coverage. A rollout decision would require explicit approval and full regression testing. No automatic deployments or percentage changes to production predictions are authorized by this document.

## Verification

- Existing shadow tracker unit tests continue passing.
- Added `tests/test_test_c_challenger.py` for switched winners, corrections, new errors, original-side value compatibility, pending results and immutable snapshot behavior.
- `.github/workflows/test-c-leading-challenger.yml` audits the original 112-game 2026 archive against independently established metrics.
- The regular capture workflow is restricted to main-branch pushes; research-branch CI cannot accidentally write to main.

**Source head-to-head:** [2026 Weeks 3–6 Test C vs V1.5](https://github.com/christianmellis1-debug/CFB_Prediction_app/blob/research/test-c-head-to-head-weeks3-6-2026-10-13/research/TEST_C_V15_WEEKS3_6_REPORT.md).
