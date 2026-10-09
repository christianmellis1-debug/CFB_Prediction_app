# 2026 Weeks 3–5 · Value Shortlist ROI reconstruction

Research run: 2026-10-09 19:46:51 UTC. [Successful GitHub Actions run](https://github.com/christianmellis1-debug/CFB_Prediction_app/actions/runs/37982493865). Generated with `run.py` using the production V1.5 model, current five-stage waterfall, ESPN archived per-event sportsbook quotes, historical weather verification, and `value_roi.py`.

> **Retrospective reconstruction, not a prospective betting record.** These are the selections that today's rules identify using earlier-week stats; they were not all saved before kickoff. Archived odds are not proof of a wagerable pregame price. The rules have been researched and refined using historical game outcomes, so these results cannot reliably predict future ROI.

## Flat $100 per recommended selection

| Week | Selections | W–L–P | Staked | Returned | Net profit | ROI |
|---|---:|---:|---:|---:|---:|---:|
| 3 | 5 | 4–1–0 | $500.00 | $625.94 | +$125.94 | +25.19% |
| 4 | 12 | 10–1–1 | $1,200.00 | $1,525.66 | +$325.66 | +27.14% |
| 5 | 16 | 14–2–0 | $1,600.00 | $2,175.62 | +$575.62 | +35.98% |
| **Total** | **33** | **28–4–1** | **$3,300.00** | **$4,327.22** | **+$1,027.22** | **+31.13%** |

## By official tier

| Tier | Selections | W–L–P | Stake | Net profit | ROI |
|---|---:|---:|---:|---:|---:|
| Tier 1 · Complete Game | 14 | 10–4–0 | $1,400.00 | +$503.71 | +35.98% |
| Tier 2 · Storm Front | 2 | 1–0–1 | $200.00 | +$90.91 | +45.46% |
| Tier 3 · Takeaway Trouble | 1 | 1–0–0 | $100.00 | +$110.00 | +110.00% |
| Tier 4 · Parlay Bridge | 12 | 12–0–0 | $1,200.00 | +$193.23 | +16.10% |
| Tier 5 · Home Turf Hammer | 4 | 4–0–0 | $400.00 | +$129.37 | +32.34% |

## Calculation and coverage

- $100 separately staked on each selected recommended market; not on the core model winner when it differs.
- Tier 1–2 picks settle against the published point spread; Tiers 3–5 settle using the selected moneyline.
- Positive American odds: profit = stake × odds / 100. Negative odds: profit = stake × 100 / absolute odds.
- Profit rounded to cents per winning bet. Losing wager loses full stake. Push refunds the stake (zero profit), with stake included in ROI denominator.
- No parlays, reinvestment, taxes, fees, rebates, bonuses, slippage, or wager limits.
- Archive retrieved 171 event summaries and at least one quote from every event; **all 33 reconstructed selected bets had usable prices** and settled scores.
- Weather-qualified candidate coverage: Week 3, 5/5 verified; Week 4, 8/8; Week 5, 12/13. The single unverified Week 5 weather candidate fails the official eligibility check, but means the historical candidate universe is not perfectly complete.
- Odds reflect ESPN's archived event summaries, not independently verified opening or closing prices; some archived prices may differ from those available when a real bet could have been placed.
- **Small and post-hoc sample.** In particular Tier 3 has one selected game and Tier 2 has only two. Avoid treating high ROI from these groups as repeatable expectations.

See [all 33 individual selections and payout calculations](value_roi_100_stake.csv).
