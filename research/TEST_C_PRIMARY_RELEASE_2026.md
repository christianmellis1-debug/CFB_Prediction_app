# Test C primary prediction rollout — October 13, 2026

## Decision
Deploy **Test C Market Blend** as the primary *straight-up winner and probability* on eligible scheduled 2026 matches and later, based on the user's explicit preference to use the leading validated historical challenger. This change is an informed practical choice, not a claim of statistical certainty.

### Fixed model
`P_TestC(home) = 0.16927926947215113 × P_V1.5(home) + 0.83072073052784887 × P_no_vig_book_home`

The no-vig home probability comes from both team moneylines **from a single verified provider**. ESPN's DraftKings data are preferred; clearly labeled same-book fallbacks are permitted. Both prices must be valid American moneylines, with 0–16% bookmaker margin. No different-book stitching.

### Eligibility and reliability
- Apply the primary blend to matchups with **scheduled kickoffs after October 13, 2026 at 18:00 UTC**, with fresh, currently available valid paired pregame odds, and whose status is "Awaiting final".
- **Do not blend when odds are missing or marked stale**, kickoff time is unavailable, or prices cannot be verified. Keep independent V1.5 winner and probability.
- At or after kickoff, use Test C **only** if a first-captured immutable pregame snapshot is present, correctly aligned with the game/teams, and captured before kickoff; otherwise retain V1.5. The archived first-quote snapshot is not a claim to have captured the final closing line.
- Games before activation remain historical V1.5. This is not a retroactive rewrite of older official predictions.
- The algorithm preserves the independent V1.5 home/away probabilities, winner, confidence, explanation and model version in `V1.5 ...` fields.
- Recalculate final `Pick Result` for a frozen Test C result when the chosen winner changes.
- Cards explain market contribution and explicitly identify disagreement with V1.5.

### Betting-integrity separation
- **All six tiers** and tier-specific outcomes are computed before Test C modifies the straight-up display result, using the existing independent matchup/ATS/moneyline rules. Their selections, pricing, and labels remain untouched.
- The `Model Edge` and `Expected Value` fields on a Test C selected winner use the *independent V1.5 side probability* and that side's actual moneyline. Do not mistake the largely market-sourced Test C probability for independent bookmaker value.
- When the Test C winner differs from the separate betting tier's recommended side, both may legitimately appear on the same game: the first is a straight-up forecast, the second is a separately tested market-specific tier recommendation.
- All historical seasonal result reconstructions are still V1.5 unless and until a verified frozen post-activation Test C source exists; the shadow dashboard independently tracks both models.

### Historical decision basis
Full-season retrospectively reconstructed 2024/2025 matched opening-odds cohorts: V1.5 1010/1437 (70.3%) versus Test C 1036/1437 (72.1%); **+26 winners** and lower Brier **0.1829 vs 0.1929**. Results depend on archive revisions and historical price availability. Exact matched-pick p≈0.09; this is promising but not proof of superiority. Test C stays under prospective observation.

### Verified tests
- Full app regression suite and six dedicated new market-prediction production tests passed on `feature/test-c-primary-market-blend-2026-10-13`.
- Covers switched winners, no independent Edge contamination, independent six-tier preservation, stale/missing quote fallback, historic non-backfill, frozen pregame quotes and outcomes, source-specific labels, and non-mutation of inputs.
- Changes limited to `app.py`, new `primary_market_blend.py`, dedicated tests, and CI/release documentation. Underlying `model_v1_5.py` and tier rule engine are unchanged.

## Rollback
Revert the merge commit containing this feature or remove the call to `apply_primary_blend` from `app.py`; V1.5 itself remains intact and can be restored without recalibrating tiers or recalculating historical observations. Keep the existing shadow tracker and original betting-tier code.

## Source
[Leading challenger specification](https://github.com/christianmellis1-debug/CFB_Prediction_app/blob/main/research/TEST_C_LEADING_CHALLENGER.md) · [Historical deployment research](https://github.com/christianmellis1-debug/CFB_Prediction_app/blob/research/test-c-historical-blend-2024-2025-2026-10-13/research/TEST_C_2024_2025_DEPLOYMENT_DECISION.md)
