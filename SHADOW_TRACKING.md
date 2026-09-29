# Prospective value-selection comparison

Experiment: `v15-market-blend-2026-09-28`. Research only; production predictions and value labels are unchanged.

- Frozen baseline: V1.5 and input preprocessing copied from app commit `11f97287787a51d742a9b25b39227afe0b9afded`.
- Blend: 0.16927926947215113 × baseline probability + 0.8307207305278489 × same-book, two-sided normalized implied probability. Weight fitted to 2024 opening odds; not refitted prospectively.
- Preserve the baseline winner, even if the blended probability falls below 50%.
- Lock each game's first eligible observation within 7 days of kickoff. Both ESPN pregame status and confirmed future ESPN/schedule kickoff required. No historical backfill and no replacing saved picks as odds move.
- Prefer DraftKings, then alphabetically first provider with valid prices for both teams. Retain bookmaker, both prices, capture time, kickoff, model probabilities, labels, input hashes and cutoff. Capture time is not a bookmaker update timestamp.
- Current-season summaries use only through-week < target week. Prior-season profiles and the baseline schedule-derived fallback remain unchanged. Source input hashes identify fetched datasets; the locked output is the authoritative prospective record.
- Same original value rules: Strong value p≥.70, edge≥.03, EV>0; otherwise Value p≥.60, edge≥.02, EV>0. Edge uses raw implied odds, not normalized market probability.
- Compare Brier score on the common settled cohort. Compare each method's selected bets at $10 flat, rounding winning profit to cents per bet. No fees, bonuses, parlays or reinvestment. Ties refund stakes and are excluded from ROI denominator and Brier score. Missing, canceled and unconfirmed results remain ungraded.
- Snapshot fields are immutable; final results live separately. Existing final results are not silently rewritten. Corrections require a documented review.
- Scheduled checks at 02:17, 08:17, 14:17 and 20:17 UTC. Actions can be delayed; no claim of exact closing odds. Public-repository standard runners only; workflow skips private repositories. No paid APIs.
- `Model results → Forward test` displays coverage, last check, comparative results and a JSON download. Results are descriptive; small samples cannot establish profit or justify replacing the production model. No early stopping or weight optimization based on a good week.

Run `python -m unittest discover -s tests -p 'test_shadow_tracking.py'`, then `python capture_shadow.py`. GitHub Actions persists `data/shadow_tracking.json`. Failed runs appear in Actions; the UI's last-check timestamp remains unchanged when the collector fails.
