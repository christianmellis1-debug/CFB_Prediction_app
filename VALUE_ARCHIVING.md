# Saturday Forecast — prospective official value-tier archive

This is an independent research ledger, not a source of recommendations.
**No model, tier, or Streamlit app selection rules are changed by the archive.**

## Capture lifecycle

- GitHub Actions runs production model_v1_5.predict_week and model_v1_5.add_waterfall_value against fresh schedule, weekly summaries, ESPN box scores, odds, and weather.
- Events become eligible within **18 hours before kickoff**, requiring ESPN to independently confirm pregame status, future kickoff, and matching team IDs.
- Each event's first eligible observation freezes the tier (or not selected), selected team and market, actual spread/ML and payout price, provider, capture time, kickoff, confidence, and input/code provenance.
- The saved snapshot is never replaced. Final scores and grades live separately.
- Missing odds, missing prices, and ungraded cases are visible; they are never silently counted as wins or losses.
- No historical tier snapshots are forged from after-the-fact data.

## Where it runs

- Archive: data/value_archive_2026.json
- Collector: capture_value.py
- Settlement and ROI validation: value_archive.py
- Scheduled UTC checks: 01:43, 07:43, 13:43, 19:43, plus GitHub Actions manual trigger.
- Scheduling depends on GitHub Actions and free public data. Checks may be delayed.
- Collector runs separately from Streamlit so user page visits do not mutate historical results.
- Snapshots represent the scheduled collector's observed prices, not necessarily each viewer's exact displayed line.

## Auditing

Use locked pregame snapshots for verified official five-tier forward records.
Grades: ATS for Tier 1 and Tier 2; moneyline straight-up for Tier 3 through Tier 5.
Pushes are excluded from win-loss rates. Hypothetical ROI includes only settled
picks with a valid original price; winnings are rounded per bet and stakes are
included in the denominator. Disclose missing/late data and skipped captures.

The Week 6 2026 analysis in research/week6_value_tier_audit.py is a
**retrospective reconstruction**, not an official locked Week 6 selection
record. Its moneylines are sourced from the already saved frozen V1.5
forward test, but original Tier 1/2 spread quotes and historical forecast
snapshots were not preserved. Do not report its tier win rates as prospective
performance.

## Safety / privacy / regression

This is a public repository and does not hold customer data, secrets, or
account credentials. It does not alter existing predictions, tiers or UI.
Test with test_value_archive.py and test_waterfall.py.
